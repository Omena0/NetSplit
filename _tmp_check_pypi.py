import urllib.request
import sys
url='https://pypi.org/pypi/PyNetSplit/3.6.0/json'
try:
    with urllib.request.urlopen(url, timeout=10) as r:
        print('FOUND')
except Exception as e:
    print('NOT FOUND', e)
