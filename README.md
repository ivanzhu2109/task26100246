# commission-calendar

订阅佣金日历库：给定完整、只读的订阅快照，按自然月计算每个伙伴每笔订阅的
应计佣金（整数美分）。全部计算在内存中完成，结果精确到美分，无数值误差容差。

## 安装与依赖

纯 Python 3.10+，仅依赖标准库。把 `commission_calendar/` 目录加入包路径即可：

```python
from commission_calendar import (
    CommissionCalendar, PriceRecord, Snapshot, Subscription, Window,
)
```

## 快速开始

```python
from datetime import date
from commission_calendar import (
    CommissionCalendar, PriceRecord, Snapshot, Subscription, Window,
)

snapshot = Snapshot((
    Subscription(
        txn_id="T0001",                 # 唯一 ASCII 交易编号
        partner_id="PARTNER-A",         # 伙伴标识
        deal_date=date(2024, 1, 31),    # 成交日 = 服务起始日
        window=Window.MONTHS_12,        # 6 / 12 / 24 个订阅月或 LIFETIME
        price_records=(                 # 必须从成交日开始，生效日不重复
            PriceRecord(date(2024, 1, 31), 10000),   # 月经常性收入（美分，>=0）
            PriceRecord(date(2024, 4, 15), 15000),   # 变价
        ),
        cancel_date=date(2024, 9, 1),   # 可选；当天零时终止资格
    ),
))

cal = CommissionCalendar(snapshot)      # 校验快照、确定阶梯费率、预计算
result = cal.query(date(2024, 1, 1), date(2025, 1, 1))  # [起始月, 结束月)

result.months                # 逐自然月（每月1日），含起始月、不含结束月
result.amounts["T0001"]      # 与 months 对齐的逐月佣金（整数美分）
result.total("T0001")        # 区间合计
```

## 业务规则要点

- **阶梯费率**：同一伙伴按（成交日，交易编号 ASCII 字典序）排序，前 10 笔
  10%，第 11 笔起 15%；取消的订阅仍占序位；输入顺序不影响结果。
- **订阅月**：以原始起始日日号为锚逐月推进；目标月无该日号时取月末，
  之后仍用原始日号（1月31日 → 2月28/29日 → 3月31日）。订阅月含起始日、
  不含下一边界日。
- **资格终止**：佣金窗口终点（第 N 个边界日）与取消日取较早者，终止日当天
  零时起不计佣金。
- **精确计提**：某日应计 = 当日月经常性收入 × 费率 ÷ 当日所属完整订阅月
  天数；变价、取消、窗口到期不改变分母。全程用分数精确运算，只在自然月
  末对"自服务起始日起的累计值"做四舍五入（半美分向上），本月入账 =
  本月末与上月末两个已舍入累计值之差。因此任意拆分查询再合并，结果与
  整段查询逐月完全一致；从历史中间开始查询也不会重新起算。

## 运行测试

```bash
python3 -m pytest tests/ -q
```

- `tests/test_calendar.py`：订阅月边界（含闰年、月末锚点）。
- `tests/test_engine.py`：阶梯归属（同日成交跨第10/11笔且前序取消）、
  半美分舍入、微小金额长期积累、拆分/整段查询一致、输入校验。
- `tests/test_reference.py`：与独立的逐日精确计提参考实现对照
  （含月底起始跨闰年、变价恰逢月锚/资格终止的组合及随机用例）。
- `tests/test_performance.py`：可重复性能测试——10000 笔订阅、每笔最多
  20 次变价、30 年历史，查询末尾连续 12 个自然月（含首次计算），
  预算 10 秒（实测约 2 秒）。
