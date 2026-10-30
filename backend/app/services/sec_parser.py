import os
import re
import json
import logging
import tempfile
import requests
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from pathlib import Path
import zipfile
import io

# Arelle is optional - SEC XBRL parsing requires arelle
try:
    from arelle import Cntlr
    from arelle.ModelDocument import Type
    from arelle.ModelInstanceObject import ModelFact
    from arelle.ModelValue import QName
    ARELLE_AVAILABLE = True
except ImportError:
    Cntlr = None
    Type = None
    ModelFact = None
    QName = None
    ARELLE_AVAILABLE = False

from app.services.sec_tags import tag_resolver
from app.core.config import settings

logger = logging.getLogger(__name__)

SEC_BASE_URL = "https://www.sec.gov"
SEC_ARCHIVES_URL = "https://www.sec.gov/Archives"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions"
SEC_USER_AGENT = getattr(settings, "sec_user_agent", "StockAgent/1.0 (admin@yourdomain.com)")


@dataclass
class FilingInfo:
    accession_number: str
    filing_date: date
    report_date: date
    form_type: str
    fiscal_year: int
    fiscal_period: str
    primary_document: str
    amendment_flag: bool = False


@dataclass
class ParsedFiling:
    ticker: str
    cik: str
    filing_info: FilingInfo
    metrics: Dict[str, Tuple[Optional[float], Optional[str]]]
    raw_facts: Dict[str, Any]
    contexts: Dict[str, Dict]
    units: Dict[str, str]
    knowledge_timestamp: datetime


class SECEdgarParser:
    def __init__(self, cache_dir: str = "/tmp/sec_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": SEC_USER_AGENT})
        self._cik_cache: Dict[str, str] = {}

    def get_cik(self, ticker: str) -> Optional[str]:
        if ticker in self._cik_cache:
            return self._cik_cache[ticker]
        
        url = f"{SEC_SUBMISSIONS_URL}/CIK{ticker}.json"
        try:
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                cik = str(data.get("cik", "")).zfill(10)
                self._cik_cache[ticker] = cik
                return cik
        except Exception as e:
            logger.warning(f"Failed to get CIK for {ticker}: {e}")
        
        return None

    def get_company_filings(self, cik: str, forms: List[str] = None) -> List[FilingInfo]:
        if forms is None:
            forms = ["10-K", "10-Q"]
        
        url = f"{SEC_SUBMISSIONS_URL}/CIK{cik}.json"
        try:
            resp = self.session.get(url, timeout=30)
            if resp.status_code != 200:
                return []
            
            data = resp.json()
            filings = []
            
            recent = data.get("filings", {}).get("recent", {})
            for i in range(len(recent.get("accessionNumber", []))):
                form = recent["form"][i]
                if form not in forms:
                    continue
                
                accession = recent["accessionNumber"][i].replace("-", "")
                filing_date = datetime.strptime(recent["filingDate"][i], "%Y-%m-%d").date()
                report_date = datetime.strptime(recent["reportDate"][i], "%Y-%m-%d").date()
                primary_doc = recent["primaryDocument"][i]
                
                fiscal_years = recent.get("fiscalYear", [])
                fiscal_periods = recent.get("fiscalPeriod", [])
                fiscal_year = int(fiscal_years[i]) if i < len(fiscal_years) and fiscal_years[i] else filing_date.year
                fiscal_period = fiscal_periods[i] if i < len(fiscal_periods) else ""
                
                filings.append(FilingInfo(
                    accession_number=accession,
                    filing_date=filing_date,
                    report_date=report_date,
                    form_type=form,
                    fiscal_year=fiscal_year,
                    fiscal_period=fiscal_period,
                    primary_document=primary_doc,
                ))
            
            return filings
        except Exception as e:
            logger.error(f"Failed to get filings for CIK {cik}: {e}")
            return []

    def download_filing(self, cik: str, accession: str, primary_doc: str) -> Optional[bytes]:
        url = f"{SEC_ARCHIVES_URL}/edgar/data/{int(cik)}/{accession}/{primary_doc}"
        try:
            resp = self.session.get(url, timeout=60)
            if resp.status_code == 200:
                return resp.content
        except Exception as e:
            logger.warning(f"Failed to download {url}: {e}")
        return None

    def parse_xbrl(self, xbrl_content: bytes) -> Tuple[Dict, Dict, Dict]:
        facts = {}
        contexts = {}
        units = {}
        
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
            tmp.write(xbrl_content)
            tmp_path = tmp.name
        
        try:
            cntlr = Cntlr.Cntlr(logFileName="logToPrint")
            model_xbrl = cntlr.modelManager.load(tmp_path)
            
            for fact in model_xbrl.facts:
                if not isinstance(fact, ModelFact):
                    continue
                
                concept = fact.concept
                if concept is None:
                    continue
                
                qname = concept.qname
                tag = f"{qname.namespaceURI}:{qname.localName}" if qname.namespaceURI else qname.localName
                
                value = fact.value
                if value is None:
                    continue
                
                try:
                    if isinstance(value, (int, float)):
                        numeric_value = float(value)
                    else:
                        numeric_value = float(str(value).replace(",", ""))
                except (ValueError, TypeError):
                    continue
                
                context_id = fact.contextID
                unit_id = fact.unitID
                
                if tag not in facts:
                    facts[tag] = []
                facts[tag].append({
                    "value": numeric_value,
                    "context": context_id,
                    "unit": unit_id,
                })
                
                if context_id not in contexts and fact.context is not None:
                    ctx = fact.context
                    contexts[context_id] = {
                        "entity": ctx.entityIdentifier[1] if ctx.entityIdentifier else None,
                        "period_start": ctx.startDatetime.isoformat() if ctx.startDatetime else None,
                        "period_end": ctx.endDatetime.isoformat() if ctx.endDatetime else None,
                        "instant": ctx.instantDatetime.isoformat() if ctx.instantDatetime else None,
                        "scenario": str(ctx.scenario) if ctx.scenario else None,
                    }
                
                if unit_id not in units and fact.unit is not None:
                    units[unit_id] = str(fact.unit)
            
            consolidated_facts = {}
            for tag, entries in facts.items():
                consolidated_facts[tag] = self._select_best_fact(entries, contexts)
            
            return consolidated_facts, contexts, units
            
        except Exception as e:
            logger.error(f"XBRL parsing error: {e}")
            return {}, {}, {}
        finally:
            try:
                os.unlink(tmp_path)
            except:
                pass

    def _select_best_fact(self, entries: List[Dict], contexts: Dict) -> Optional[float]:
        best_entry = None
        best_score = -1
        
        for entry in entries:
            context_id = entry["context"]
            context = contexts.get(context_id, {})
            
            score = 0
            
            if context.get("scenario") is None:
                score += 10
            
            period_end = context.get("period_end")
            instant = context.get("instant")
            if period_end:
                try:
                    dt = datetime.fromisoformat(period_end.replace("Z", "+00:00"))
                    score += 5
                except:
                    pass
            
            if entry["unit"] and "USD" in str(entry["unit"]).upper():
                score += 3
            
            if score > best_score:
                best_score = score
                best_entry = entry
        
        return best_entry["value"] if best_entry else None

    def parse_filing(self, ticker: str, filing: FilingInfo) -> Optional[ParsedFiling]:
        cik = self.get_cik(ticker)
        if not cik:
            logger.warning(f"No CIK found for {ticker}")
            return None
        
        xbrl_content = self.download_filing(cik, filing.accession_number, filing.primary_document)
        if not xbrl_content:
            logger.warning(f"Failed to download filing for {ticker} {filing.accession_number}")
            return None
        
        facts, contexts, units = self.parse_xbrl(xbrl_content)
        if not facts:
            logger.warning(f"No facts extracted for {ticker} {filing.accession_number}")
            return None
        
        metrics = {}
        for metric in tag_resolver.mappings.keys():
            value, tag_used = tag_resolver.extract_metric(facts, metric)
            metrics[metric] = (value, tag_used)
        
        tag_resolver.record_coverage(ticker, str(filing.filing_date), metrics)
        
        return ParsedFiling(
            ticker=ticker,
            cik=cik,
            filing_info=filing,
            metrics=metrics,
            raw_facts=facts,
            contexts=contexts,
            units=units,
            knowledge_timestamp=datetime.combine(filing.filing_date, datetime.min.time()),
        )


sec_parser = SECEdgarParser()