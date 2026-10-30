import re

with open(r'C:\Users\Vijaykumar\stock-agent\backend\.venv\Lib\site-packages\sqlalchemy\util\langhelpers.py', 'r') as f:
    content = f.read()

# Find and patch the _IntFlagMeta.__init__ method
old_code = '''        for k, v in dict_.items():
            if re.match(r"^__.*__$", k):
                continue'''

new_code = '''        for k, v in dict_.items():
            if re.match(r"^__.*__$", k) or k == "__firstlineno__":
                continue'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open(r'C:\Users\Vijaykumar\stock-agent\backend\.venv\Lib\site-packages\sqlalchemy\util\langhelpers.py', 'w') as f:
        f.write(content)
    print('Patched langhelpers.py successfully')
else:
    print('Pattern not found, searching for alternative...')
    # Try to find the pattern
    for i, line in enumerate(content.split('\n')):
        if 're.match(r"^__.*__$"' in line:
            print(f'Found at line: {line.strip()}')