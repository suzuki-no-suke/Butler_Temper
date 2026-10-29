"""LLM API の疎通確認。設定されている API キーごとに、モデル一覧の取得と最小の呼び出しを行う。

使い方（リポジトリ直下で実行）:
    npm run check:connectivity
"""

import sys

import anthropic
import typesafe_sdk

from bt_backend.config import get_settings


def check_anthropic(key: str) -> None:
    client = anthropic.Anthropic(api_key=key, max_retries=0)
    ids = [m.id for m in client.models.list(limit=100)]
    print(f"  モデル一覧: {', '.join(ids)}")
    reply = client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=64,
        messages=[{"role": "user", "content": "「疎通確認OK」とだけ返してください。"}],
    )
    text = "".join(b.text for b in reply.content if b.type == "text")
    print(f"  claude-sonnet-5-5 の応答: {text!r}（model={reply.model}）")


def check_typesafe(key: str) -> None:
    with typesafe_sdk.TypeSafeClient(
        api_key=key, retry=typesafe_sdk.RetryPolicy(max_retries=0)
    ) as client:
        models = client.models.list().models
        print("  モデル一覧: " + ", ".join(f"{m.name}（{m.release_date}）" for m in models))
        result = client.system_one(
            state={"conversation": [{"speaker": "主人", "text": "いつも本当にありがとう"}]},
            questions={"thanks": typesafe_sdk.Noul(instructions="主人は執事に感謝を伝えている。")},
        )
        print(f"  Jev の応答: thanks={result.nouls['thanks'].noul:.3f}（model={result.model}）")


def main() -> int:
    settings = get_settings()
    checks = [
        ("Anthropic", settings.anthropic_api_key, check_anthropic),
        ("TypeSafe AI", settings.typesafe_api_key, check_typesafe),
    ]
    failed = False
    for name, key, check in checks:
        print(f"[{name}]")
        if not key:
            print("  API キーが設定されていないため飛ばします")
            continue
        try:
            check(key)
            print("  OK")
        except Exception as e:  # noqa: BLE001 - 失敗の内容をそのまま表示する
            failed = True
            print(f"  失敗: {type(e).__name__}: {e}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
