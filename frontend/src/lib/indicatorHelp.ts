/** 指标说明（移植自旧版 indicator_help.py），供各指标名旁的 ⓘ 弹层使用。不构成投资建议。 */
export interface IndicatorHelp {
  title: string
  formula?: string
  points: string[]
}

export const INDICATOR_HELP = {
  ma: {
    title: '移动平均线（MA）',
    formula: 'MAₙ = (P₁ + P₂ + … + Pₙ) ÷ n',
    points: ['最近 n 个交易日收盘价的算术平均值，用于平滑短期波动、观察趋势。', '均线交叉属于滞后信号，震荡行情中可能反复失效。'],
  },
  bbi: {
    title: 'BBI（多空指标）',
    formula: 'BBI = (MA₃ + MA₆ + MA₁₂ + MA₂₄) ÷ 4',
    points: [
      '把四条不同周期的均线合成一条趋势线，便于观察中短期多空方向。',
      '价格位于 BBI 上方且 BBI 向上为偏强参考；位于下方且 BBI 向下为偏弱参考。',
      '本质仍是移动平均线，震荡行情中可能频繁出现假突破。',
    ],
  },
  boll: {
    title: 'BOLL（布林线）',
    formula: '中轨 = MA₂₀　上轨 = 中轨 + 2σ　下轨 = 中轨 − 2σ',
    points: [
      '中轨反映价格中枢；带宽扩大通常表示波动增强，收窄表示波动减弱。',
      '价格触及上轨或下轨并不等于直接的卖出或买入信号；强趋势中价格可能持续沿轨运行。',
    ],
  },
  rsi: {
    title: 'RSI（相对强弱指标）',
    formula: 'RSI = 100 − 100 ÷ (1 + RS)',
    points: [
      'RS 是指定周期内平均上涨幅度与平均下跌幅度之比，默认周期 14 个交易日。',
      '0–30 超卖区；30–70 中性区；70–100 超买区。',
      '超买和超卖表示动能处于极端区域，不代表价格会立即反转；强趋势中 RSI 可能长时间停留在高位或低位。',
    ],
  },
  macd: {
    title: 'MACD（指数平滑异同平均线）',
    formula: 'MACD = EMA₁₂ − EMA₂₆　信号线 = EMA₉(MACD)',
    points: ['衡量短期与长期指数移动平均线的差异，适合观察趋势和动量，同样具有滞后性。', '柱 = MACD − 信号线。'],
  },
  volatility: {
    title: '年化波动率',
    formula: 'σ年化 = Std(日收益率) × √252',
    points: ['描述价格变化幅度，不区分上涨和下跌。数值越高通常意味着不确定性越大。', '它不是收益率，也不能单独用于判断股票是否值得投资。'],
  },
  pe: {
    title: '市盈率 TTM / 静态 / 动态',
    formula: 'PE = 当前总市值 ÷ 净利润',
    points: [
      'TTM 使用最近四个季度净利润，通常最接近公司当前盈利状态。',
      '静态使用最近完整财年净利润，口径稳定但可能滞后。',
      '动态把当前累计利润年化：一季报 ×4、中报 ×2、三季报 ×4/3；季节性明显的企业可能失真。',
      '净利润为零或亏损时，市盈率没有经济意义，显示“亏损/不适用”。',
    ],
  },
  week52: {
    title: '区间高低 与 52 周高低',
    points: ['区间最高 / 最低：按当前所选日期区间统计。', '52 周最高 / 最低：固定取最近一年，不随所选区间变化。'],
  },
} satisfies Record<string, IndicatorHelp>

export type IndicatorKey = keyof typeof INDICATOR_HELP
