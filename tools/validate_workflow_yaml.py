import yaml,sys
p='d:/GitHub/NetSplit/.github/workflows/publish.yml'
try:
    with open(p,'r',encoding='utf8') as f:
        yaml.safe_load(f)
    print('YAML ok')
except Exception as e:
    print('YAML parse error:', e)
    sys.exit(1)
