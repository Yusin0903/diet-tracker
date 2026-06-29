"""讓 pytest 從 repo 根目錄匯入應用模組(targets / auth / main …)。

放在根目錄的 conftest.py 會使 pytest 把此目錄加入 sys.path。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
