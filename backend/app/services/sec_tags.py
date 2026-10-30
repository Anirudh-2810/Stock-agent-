from typing import Dict, List, Optional, Tuple
import json

SEC_TAG_MAPPINGS = {
    "net_income": [
        "us-gaap:NetIncomeLoss",
        "us-gaap:ProfitLoss",
        "us-gaap:NetIncomeLossAvailableToCommonStockholdersBasic",
        "us-gaap:ComprehensiveIncomeNetOfTax",
    ],
    "revenue": [
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap:SalesRevenueNet",
        "us-gaap:Revenues",
        "us-gaap:RevenueFromContractWithCustomer",
    ],
    "total_assets": [
        "us-gaap:Assets",
        "us-gaap:AssetsTotal",
    ],
    "total_liabilities": [
        "us-gaap:Liabilities",
        "us-gaap:LiabilitiesTotal",
    ],
    "stockholders_equity": [
        "us-gaap:StockholdersEquity",
        "us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "shares_outstanding": [
        "us-gaap:CommonStockSharesOutstanding",
        "us-gaap:WeightedAverageNumberOfSharesOutstandingBasic",
    ],
    "eps_basic": [
        "us-gaap:EarningsPerShareBasic",
        "us-gaap:EarningsPerShareDiluted",
    ],
    "operating_income": [
        "us-gaap:OperatingIncomeLoss",
        "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    ],
    "cash_equivalents": [
        "us-gaap:CashAndCashEquivalentsAtCarryingValue",
        "us-gaap:Cash",
    ],
    "gross_profit": [
        "us-gaap:GrossProfit",
    ],
    "research_development": [
        "us-gaap:ResearchAndDevelopmentExpense",
    ],
    "selling_general_admin": [
        "us-gaap:SellingGeneralAndAdministrativeExpense",
    ],
    "depreciation_amortization": [
        "us-gaap:DepreciationDepletionAndAmortization",
    ],
    "interest_expense": [
        "us-gaap:InterestExpense",
    ],
    "income_tax_expense": [
        "us-gaap:IncomeTaxExpenseBenefit",
    ],
    "capital_expenditures": [
        "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
    ],
    "free_cash_flow": [
        "us-gaap:FreeCashFlow",
    ],
    "dividends_per_share": [
        "us-gaap:CommonStockDividendsPerShareDeclared",
    ],
    "book_value_per_share": [
        "us-gaap:BookValuePerShare",
    ],
}


class SECTagResolver:
    def __init__(self):
        self.mappings = SEC_TAG_MAPPINGS
        self._custom_tags: Dict[str, List[str]] = {}
        self._coverage_stats: Dict[str, Dict] = {}

    def extract_metric(self, facts: Dict, metric: str) -> Tuple[Optional[float], Optional[str]]:
        if metric not in self.mappings:
            return None, None
        
        for tag in self.mappings[metric]:
            if tag in facts:
                val = facts[tag]
                if val is not None:
                    try:
                        return float(val), tag
                    except (ValueError, TypeError):
                        continue
        
        if metric in self._custom_tags:
            for tag in self._custom_tags[metric]:
                if tag in facts:
                    val = facts[tag]
                    if val is not None:
                        try:
                            return float(val), tag
                        except (ValueError, TypeError):
                            continue
        
        return None, None

    def add_custom_tag(self, metric: str, tag: str):
        if metric not in self._custom_tags:
            self._custom_tags[metric] = []
        if tag not in self._custom_tags[metric]:
            self._custom_tags[metric].append(tag)

    def get_all_tags_for_metric(self, metric: str) -> List[str]:
        return self.mappings.get(metric, []) + self._custom_tags.get(metric, [])

    def record_coverage(self, ticker: str, filing_date: str, metrics_found: Dict[str, Tuple]):
        if ticker not in self._coverage_stats:
            self._coverage_stats[ticker] = {"filings": 0, "metrics": {}}
        
        self._coverage_stats[ticker]["filings"] += 1
        for metric, (value, tag) in metrics_found.items():
            if metric not in self._coverage_stats[ticker]["metrics"]:
                self._coverage_stats[ticker]["metrics"][metric] = {"found": 0, "tags_used": {}}
            
            if value is not None:
                self._coverage_stats[ticker]["metrics"][metric]["found"] += 1
                tag_used = tag or "unknown"
                self._coverage_stats[ticker]["metrics"][metric]["tags_used"][tag_used] = \
                    self._coverage_stats[ticker]["metrics"][metric]["tags_used"].get(tag_used, 0) + 1

    def get_coverage_report(self) -> Dict:
        report = {}
        for ticker, stats in self._coverage_stats.items():
            report[ticker] = {
                "total_filings": stats["filings"],
                "metrics": {}
            }
            for metric, mstats in stats["metrics"].items():
                report[ticker]["metrics"][metric] = {
                    "found_pct": (mstats["found"] / stats["filings"]) * 100 if stats["filings"] > 0 else 0,
                    "tags_used": mstats["tags_used"],
                }
        return report


tag_resolver = SECTagResolver()