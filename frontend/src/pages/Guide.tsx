import {useEffect} from 'react';
import {Link, useLocation} from 'react-router-dom';
export default function Guide() {
  const location = useLocation();
  useEffect(() => {
    if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView({block: 'start'});
  }, [location.hash]);
  return <section className="guide-page">
    <p className="eyebrow">帮助与安全说明</p><h1>使用手册</h1>
    <p>按顺序完成一次测量；首次使用可先用合成回放熟悉流程。分析结果仅供记录和辅助查看。</p>
    <nav className="guide-toc" aria-label="手册目录"><strong>目录</strong><a href="#guide-start">开始使用</a><a href="#guide-models">分析模型</a><a href="#guide-results">记录结果</a><a href="#guide-safety">安全与共享</a></nav>
    <h2 className="guide-chapter-heading" id="guide-start">一、开始使用</h2>
    <div className="guide-grid">
      <article><span>01</span><h2>创建本地账号</h2><p>注册并登录。不同家庭成员使用各自账号；个人中心可以修改用户名、密码、字号，以及填写年龄和性别。</p></article>
      <article><span>02</span><h2>采集或导入</h2><p>使用 ADS1292R 时，先在系统完成蓝牙配对或连接 USB，回到实时监测页刷新串口并选择设备端口。开始采集后检查波形，结束时保存为记录。没有设备可在导入页选择 CSV，或先使用合成回放。</p><p>采样率填写设备真实数值。模型要求 500 Hz 时，不能通过改填数字来替代实际重采样。记录名称可留空，系统会按日期及当天次数命名。</p><Link to="/monitor">前往实时测量 →</Link></article>
      <article><span>03</span><h2>查看记录</h2><p>分析任务结束后，打开历史记录，查看波形、心率、信号质量及模型结果。心率为空或分类缺失时，先查看页面原因：可能是信号质量不足，或本次没有获得模型结果。</p><p>在详情页可修改名称，填写测量时的活动和感受、添加备注；新增的身体状况保存后可在以后记录中多选。需要换模型时使用“重新分析”；旧记录不会自动改变。</p><Link to="/records">前往历史记录 →</Link></article>
      <article><span>04</span><h2>家庭共享</h2><p>邀请已注册的家属；对方接受后才能查看共享记录。你可以撤回授权，对方也可以退出共享。分享前确认对方身份。</p><Link to="/family">前往家庭协同 →</Link></article>
    </div>
    <section className="guide-models" id="guide-models"><h2>二、按你的需要选择分析方式</h2><p>先确认自己想解决什么问题，再到“导入与分析”选择对应方式。所有结果都需要结合波形和身体感受查看。</p>
      <div className="guide-model-list">
        <article><h3>我想知道每次心跳的大致类别</h3><p>选择 CNN H27。它对逐拍标出 N/S/V/F 四类，适合逐个回看心拍和波形；输入需为真实的 500 Hz 数据。</p></article>
        <article><h3>我想换一种方式复查逐拍结果</h3><p>选择 HGB v92。它输出 N/S/VF 三类，其中 VF 是合并类，不能当作某一种具体心拍的诊断；同样要求真实 500 Hz 输入。</p></article>
        <article><h3>我想同时看两种逐拍模型是否一致</h3><p>选择“CNN 主判 + HGB 复核”。页面以 CNN 为主，HGB 提供一致性线索；两者不一致时请回看波形，不表示自动得出更确定的结论。</p></article>
        <article><h3>我想了解一段记录的整体节律</h3><p>选择 OpenECG。它分析整段节律，不逐拍给出 N/S/V/F；需要真实 500 Hz、至少 10 秒的单导联 mV 数据，且以页面可用状态为准。</p></article>
        <article><h3>我只想先检查文件和波形</h3><p>选择“仅信号检查”。页面会检查时长、数值和平直片段，不生成 AI 分类标签，适合首次导入时核对数据。</p></article>
      </div>
    </section>
    <section className="guide-models" id="guide-results"><h2>三、记录详情怎么看</h2><p>波形展示测量到的信号；心率按可检测到的心拍估算，缺失时显示“—”。质量提示只说明基础工程检查或本次信号能否继续分析，不表示临床合格。逐拍结果可展开查看心拍数量和类别；整段节律与呼吸结果仅在相应分析器实际运行时显示。</p><p>历史趋势按日期汇总可用心率，比较时留意运动、姿势和测量时长。备注及身体状况由用户填写，不是模型判断。</p></section>
    <div className="guide-safety" id="guide-safety"><h2>四、安全与共享说明</h2>
      <p>本项目用于记录和辅助查看心电数据，页面上的分类、质量评分与解释不能单独用于诊断、排除疾病或决定治疗。单导联和短时间记录也不能代替医疗机构检查。</p>
      <p>如果有持续或明显胸部不适、呼吸困难等急症症状，请及时联系当地急救服务，不要等待应用分析结果。</p>
      <p>家属共享涉及个人健康信息。只邀请信任的人，并定期查看授权状态；不再需要共享时及时撤回。</p>
      <p className="guide-sources">安全说明参考：<a href="https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpcd/classification.cfm?id=QDA" target="_blank" rel="noreferrer">FDA 对消费级心电软件的用途界定</a>；<a href="https://www.heart.org/en/health-topics/heart-attack/warning-signs-of-a-heart-attack" target="_blank" rel="noreferrer">美国心脏协会的急症症状说明</a>。</p>
    </div>
  </section>;
}
