"""NLH（ノーリミット・ホールデム）のドローシミュレータ。普通の乱数で動き、LLM は使わない。

今のハンドとボードから、ボードの残り（5 枚になるまで）とランダムなハンドを配って役を比べることを、
指定の回数だけ繰り返す。ベットのラウンドは無い（全員がリバーまで残る）。
ポジションは記録と表示のためのもので、勝敗には関わらない。

カードはランク 1 文字（2〜9, T, J, Q, K, A）とスート 1 文字（s, c, d, h）の 2 文字で書く。
ハンドに X と書くと、毎回ランダムな 2 枚になる。
"""

from collections import Counter
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from bt_backend.simulators import chance
from bt_backend.simulators.base import (
    NLH_HARD_LIMIT,
    InvalidArguments,
    SimulationOutput,
    Simulator,
    SimulatorArgs,
)

RANKS = "23456789TJQKA"
SUITS = "scdh"
RANDOM_HAND = "X"
# ボードとして受け付ける枚数（プリフロップ・フロップ・ターン・リバー）
BOARD_SIZES = (0, 3, 4, 5)

Position = Literal["UTG", "UTG+1", "UTG+2", "LJ", "HJ", "CO", "BTN", "SB", "BB"]
HERO = "Hero"

CATEGORY_NAMES = (
    "ハイカード",
    "ワンペア",
    "ツーペア",
    "スリーカード",
    "ストレート",
    "フラッシュ",
    "フルハウス",
    "フォーカード",
    "ストレートフラッシュ",
)

Card = tuple[int, str]


class NlhVillain(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: Position = Field(description="ポジション")
    hand: str = Field(description='ハンド 2 枚（例: "KsKd"）。"X" ならランダム')


class NlhArgs(SimulatorArgs):
    hero_hand: str = Field(description='Hero のハンド 2 枚（例: "AhAd"）。"X" ならランダム')
    villains: list[NlhVillain] = Field(
        min_length=1, max_length=8, description="Villain のポジションとハンド"
    )
    board: str = Field(
        default="", description='今のボード（0・3・4・5 枚。例: "7s7h7d"）。空ならプリフロップ'
    )
    hero_position: Position | None = Field(default=None, description="Hero のポジション")
    runs: int | None = Field(
        default=None,
        ge=1,
        le=NLH_HARD_LIMIT,
        description=f"シミュレートする回数（{NLH_HARD_LIMIT} 回まで。既定はグローバル設定）",
    )


def parse_cards(text: str) -> list[Card]:
    """カードの並びを読む。空白は無視する。"""
    s = "".join(text.split())
    if len(s) % 2 != 0:
        raise ValueError(f"カードは 2 文字ずつで書いてください: {text!r}")
    cards: list[Card] = []
    for i in range(0, len(s), 2):
        rank, suit = s[i].upper(), s[i + 1].lower()
        if rank not in RANKS or suit not in SUITS:
            raise ValueError(f"カードとして読めません: {s[i : i + 2]!r}")
        cards.append((RANKS.index(rank) + 2, suit))
    return cards


def card_text(card: Card) -> str:
    return RANKS[card[0] - 2] + card[1]


def cards_text(cards: list[Card]) -> str:
    return " ".join(card_text(c) for c in cards)


def _parse_hand(text: str, who: str) -> list[Card] | None:
    if text.strip().upper() == RANDOM_HAND:
        return None
    try:
        cards = parse_cards(text)
    except ValueError as e:
        raise InvalidArguments(f"{who}のハンド: {e}", []) from e
    if len(cards) != 2:
        raise InvalidArguments(f'{who}のハンドは 2 枚か "X" にしてください: {text!r}', [])
    return cards


def _straight_high(ranks: set[int]) -> int | None:
    values = ranks | {1} if 14 in ranks else ranks
    for high in range(14, 4, -1):
        if all(high - i in values for i in range(5)):
            return high
    return None


def evaluate(cards: list[Card]) -> tuple[int, ...]:
    """7 枚（5 枚以上）から作れる最も強い役。大きいほど強い。先頭が役の種類。"""
    by_suit: dict[str, list[int]] = {}
    for rank, suit in cards:
        by_suit.setdefault(suit, []).append(rank)
    flush = next((sorted(r, reverse=True) for r in by_suit.values() if len(r) >= 5), None)
    if flush is not None:
        high = _straight_high(set(flush))
        if high is not None:
            return (8, high)
    ranks = sorted((r for r, _ in cards), reverse=True)
    counts = Counter(ranks)
    quads = [r for r, n in counts.items() if n == 4]
    trips = sorted((r for r, n in counts.items() if n == 3), reverse=True)
    pairs = sorted((r for r, n in counts.items() if n == 2), reverse=True)
    if quads:
        q = quads[0]
        return (7, q, max(r for r in ranks if r != q))
    if trips and (len(trips) >= 2 or pairs):
        return (6, trips[0], max(trips[1:] + pairs))
    if flush is not None:
        return (5, *flush[:5])
    high = _straight_high(set(ranks))
    if high is not None:
        return (4, high)
    if trips:
        t = trips[0]
        return (3, t, *[r for r in ranks if r != t][:2])
    if len(pairs) >= 2:
        p1, p2 = pairs[0], pairs[1]
        return (2, p1, p2, next(r for r in ranks if r not in (p1, p2)))
    if pairs:
        p = pairs[0]
        return (1, p, *[r for r in ranks if r != p][:3])
    return (0, *ranks[:5])


class NlhDrawSimulator(Simulator):
    name = "nlh_draw"
    label = "NLH ドローシミュレータ"
    description = (
        "NLH で、今のハンドとボードから残りを配って勝敗を比べることを runs 回繰り返し、"
        "Hero の勝ち・負け・引き分けの回数と勝利割合、全回の結果を返す。"
        'カードは "Ah" のように 2 文字で書き、ハンドを "X" にするとランダムな 2 枚になる。'
    )
    result_description = (
        '{"runs", "hero_wins", "hero_losses", "ties", "hero_win_rate"（勝ち / 回数。'
        '引き分けは回数に含め、勝ちに含めない）, "results"（全回の結果）}'
    )
    args_model = NlhArgs
    global_defaults = {"runs": "nlh_runs"}

    def check(self, params: dict[str, Any]) -> None:
        players = [(HERO, params["hero_position"], params["hero_hand"])] + [
            (v["position"], v["position"], v["hand"]) for v in params["villains"]
        ]
        positions = [p for _, p, _ in players if p is not None]
        if len(positions) != len(set(positions)):
            raise InvalidArguments("ポジションが重なっています", [])
        known: list[Card] = []
        for who, _, hand in players:
            cards = _parse_hand(hand, who)
            known += cards or []
        try:
            board = parse_cards(params["board"])
        except ValueError as e:
            raise InvalidArguments(f"ボード: {e}", []) from e
        if len(board) not in BOARD_SIZES:
            raise InvalidArguments("ボードは 0・3・4・5 枚のどれかにしてください", [])
        known += board
        if len(known) != len(set(known)):
            raise InvalidArguments("同じカードが二度出てきます", [])

    def run(self, params: dict[str, Any], api_keys: Mapping[str, str | None]) -> SimulationOutput:
        names = [HERO] + [v["position"] for v in params["villains"]]
        fixed = [_parse_hand(params["hero_hand"], HERO)] + [
            _parse_hand(v["hand"], v["position"]) for v in params["villains"]
        ]
        board = parse_cards(params["board"])
        used = {c for hand in fixed for c in hand or []} | set(board)
        deck = [(r, s) for r in range(2, 15) for s in SUITS if (r, s) not in used]

        results: list[dict[str, Any]] = []
        wins = losses = ties = 0
        for _ in range(params["runs"]):
            drawn = chance.rng.sample(deck, 2 * fixed.count(None) + 5 - len(board))
            hands: list[list[Card]] = []
            for hand in fixed:
                if hand is None:
                    hand, drawn = drawn[:2], drawn[2:]
                hands.append(hand)
            full_board = board + drawn
            scores = [evaluate(h + full_board) for h in hands]
            best = max(scores)
            winners = [n for n, s in zip(names, scores, strict=True) if s == best]
            if winners == [HERO]:
                wins += 1
            elif HERO in winners:
                ties += 1
            else:
                losses += 1
            results.append(
                {
                    "hero": cards_text(hands[0]),
                    "villains": [
                        {"position": n, "hand": cards_text(h)}
                        for n, h in zip(names[1:], hands[1:], strict=True)
                    ],
                    "board": cards_text(full_board),
                    "made_hands": {
                        n: CATEGORY_NAMES[s[0]] for n, s in zip(names, scores, strict=True)
                    },
                    "winners": winners,
                }
            )
        runs = params["runs"]
        return SimulationOutput(
            status="succeeded",
            result={
                "runs": runs,
                "hero_wins": wins,
                "hero_losses": losses,
                "ties": ties,
                "hero_win_rate": wins / runs,
                "results": results,
            },
        )
