import streamlit as st


def render_indicator_help():
    """Render indicator definitions as a standalone application page."""
    st.subheader("指标说明与计算方法")
    st.caption("以下内容用于理解数据口径，不构成投资建议。")

    with st.expander("价格、52 周高低点与成交量", expanded=True):
        st.markdown(
            """
            - **当前价格**：所选日期范围内最后一个交易日的收盘价。
            - **52 周最高/最低**：当前页面所加载区间内的最高价和最低价；默认选择一年时，
              可近似理解为 52 周区间。
            - **成交量**：交易期内成交的股票数量。放量上涨或下跌仍需结合趋势位置判断，
              成交量本身不直接代表买入或卖出信号。
            """
        )

    with st.expander("移动平均线（MA）"):
        st.latex(r"MA_n = \frac{P_1 + P_2 + \cdots + P_n}{n}")
        st.markdown(
            "MA 是最近 n 个交易日收盘价的算术平均值，用于平滑短期波动和观察趋势。"
            "均线交叉属于滞后信号，震荡行情中可能反复失效。"
        )

    with st.expander("BBI（多空指标）"):
        st.latex(r"BBI = \frac{MA_3 + MA_6 + MA_{12} + MA_{24}}{4}")
        st.markdown(
            """
            <div class="indicator-summary-grid">
                <div class="indicator-summary-card">
                    <strong>默认参数</strong>
                    <span>3、6、12、24 个交易日</span>
                </div>
                <div class="indicator-summary-card">
                    <strong>偏强参考</strong>
                    <span>价格位于 BBI 上方，且 BBI 向上</span>
                </div>
                <div class="indicator-summary-card">
                    <strong>偏弱参考</strong>
                    <span>价格位于 BBI 下方，且 BBI 向下</span>
                </div>
            </div>
            <div class="indicator-note">
                BBI 将四条不同周期均线合成为一条趋势线，适合快速观察中短期多空方向。
                它本质上仍是移动平均线，在震荡行情中可能频繁产生假突破。
            </div>
            """,
            unsafe_allow_html=True,
        )

    with st.expander("BOLL（布林线）"):
        st.latex(r"MID = MA_{20},\quad UP = MID + 2\sigma,\quad DOWN = MID - 2\sigma")
        st.markdown(
            """
            <div class="indicator-summary-grid">
                <div class="indicator-summary-card">
                    <strong>中轨 MID</strong>
                    <span>20 日移动平均线，反映价格中枢</span>
                </div>
                <div class="indicator-summary-card">
                    <strong>上轨 UP</strong>
                    <span>中轨 + 2 倍标准差</span>
                </div>
                <div class="indicator-summary-card">
                    <strong>下轨 DOWN</strong>
                    <span>中轨 − 2 倍标准差</span>
                </div>
            </div>
            <div class="indicator-note">
                带宽扩大通常表示波动增强，收窄表示波动减弱。价格触及上轨或下轨并不等于
                直接的卖出或买入信号；强趋势中价格可能持续沿轨运行。
            </div>
            """,
            unsafe_allow_html=True,
        )

    with st.expander("RSI（相对强弱指标）"):
        st.markdown(
            """
            <div class="rsi-formula" aria-label="RSI equals 100 minus 100 divided by 1 plus RS">
                <em>RSI</em><span>=</span><span>100</span><span>−</span>
                <span class="rsi-fraction"><span>100</span><span>1 + <em>RS</em></span></span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <div class="rsi-zone-grid">
                <div class="rsi-zone-card oversold">
                    <strong>0–30 · 超卖区</strong>
                    <span>下跌动能可能过度，关注企稳或反弹迹象</span>
                </div>
                <div class="rsi-zone-card neutral">
                    <strong>30–70 · 中性区</strong>
                    <span>多空力量相对均衡，结合趋势方向判断</span>
                </div>
                <div class="rsi-zone-card overbought">
                    <strong>70–100 · 超买区</strong>
                    <span>上涨动能可能过热，关注回调或背离风险</span>
                </div>
            </div>
            <div class="indicator-note">
                <strong>计算口径：</strong>RS 是指定周期内平均上涨幅度与平均下跌幅度之比，
                页面默认使用 14 个交易日。超买和超卖表示动能处于极端区域，不代表价格会立即反转；
                强趋势中 RSI 可能长时间停留在高位或低位。
            </div>
            """,
            unsafe_allow_html=True,
        )

    with st.expander("MACD（指数平滑异同平均线）"):
        st.latex(r"MACD = EMA_{12} - EMA_{26}")
        st.latex(r"Signal = EMA_9(MACD)")
        st.markdown(
            "MACD 衡量短期与长期指数移动平均线的差异，适合观察趋势和动量，"
            "但同样具有滞后性。"
        )

    with st.expander("年化波动率"):
        st.latex(r"\sigma_{annual} = Std(日收益率) \times \sqrt{252}")
        st.markdown(
            "年化波动率描述价格变化幅度，不区分上涨和下跌。数值越高通常意味着"
            "不确定性越大；它不是收益率，也不能单独用于判断股票是否值得投资。"
        )

    with st.expander("市盈率 TTM、静态市盈率与动态市盈率", expanded=True):
        st.markdown(
            """
            <div class="pe-formula-grid">
                <div class="pe-formula-card">
                    <div class="pe-formula-title">TTM 市盈率</div>
                    <div class="pe-formula">
                        <span>PE<sub>TTM</sub></span><span>=</span>
                        <span class="pe-fraction"><span>当前总市值</span><span>最近四个季度净利润</span></span>
                    </div>
                </div>
                <div class="pe-formula-card">
                    <div class="pe-formula-title">静态市盈率</div>
                    <div class="pe-formula">
                        <span>PE<sub>静态</sub></span><span>=</span>
                        <span class="pe-fraction"><span>当前总市值</span><span>最近完整财年净利润</span></span>
                    </div>
                </div>
                <div class="pe-formula-card">
                    <div class="pe-formula-title">动态市盈率</div>
                    <div class="pe-formula">
                        <span>PE<sub>动态</sub></span><span>=</span>
                        <span class="pe-fraction"><span>当前总市值</span><span>当前报告期年化净利润</span></span>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            - **TTM 市盈率**使用滚动十二个月利润，通常最接近公司当前盈利状态。
            - **静态市盈率**使用最近完整年报利润，口径稳定但可能滞后。
            - **动态市盈率**把当前累计利润年化：一季报 ×4、中报 ×2、三季报 ×4/3；
              季节性明显的企业可能失真。
            - 市盈率应优先与同一行业、相近商业模式和成长阶段的公司比较。
              净利润为零或亏损时，市盈率没有经济意义。
            """
        )
