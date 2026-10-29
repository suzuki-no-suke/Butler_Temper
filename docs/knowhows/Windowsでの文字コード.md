Windows での文字コード
======================

# 概要

Windows では、Python がファイルを読むときの既定の文字コードが cp932 になる。UTF-8 の日本語を含む設定ファイルは、文字コードを指定せずに読むと UnicodeDecodeError になる。

## 全体像

- alembic.ini は configparser で読まれ、文字コードを指定できない。日本語のコメントを書くと、Windows で `UnicodeDecodeError: 'cp932' codec can't decode` になる（2026-10-29 に実際に発生）
  - 対策 : alembic.ini は ASCII のみで書く。apps/backend/tests/test_config.py で確かめている
- pydantic-settings で読む env ファイルは、`env_file_encoding="utf-8"` を指定しておく
- Python のソースコード（.py）は UTF-8 として読まれるので、日本語を書いてよい
