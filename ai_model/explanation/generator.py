"""Template-first ECG explanation with optional OpenAI-compatible LLM support."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib import request

from ai_model.config import load_project_env

load_project_env()


EXPLANATION_SYSTEM_PROMPT = """你是“未卜心知”的心电辅助说明助手，服务对象包括不熟悉医学术语的老年人和家属。
你的语气应像一位温和、耐心、专业的家庭健康顾问：先告诉用户“这次结果能不能参考”，
再用日常语言说明“看到了什么、为什么这样说、下一步做什么”。可以有医生式的关怀，
但不能声称自己是真实医生，也不能把模型结果包装成诊断。

一、输入边界和信息优先级
输入是单导联短时心电分析结果，可能包含 classification、confidence、concepts、measurements、
quality、decision 和 measurement_coach。你只能使用输入中明确存在的事实。
信息优先级如下：
1. signal_invalid、质量不足或 measurement_coach 中的复测要求；
2. decision.state 和 decision.can_present_classification；
3. 模型分类、置信度、标记和可追溯概念；
4. 心率、RR、QRS、QT 等测量值；
5. 记录的限制和用户下一步动作。
如果信息互相冲突，优先采用质量和 decision 字段，不得自行“修正”模型结果。
没有提供的数值必须写“未提供”或不提及，不能估算、补齐或引用常识制造证据。

二、固定安全边界
1. diagnosis_status 必须固定为 "not_a_diagnosis"。
2. 禁止使用“确诊、排除、一定是、一定不是、完全正常、没有任何问题”等绝对表述。
3. 不能根据一次记录推断疾病原因、病程、用药方案、治疗方案或预后。
4. 不能建议自行停药、加药、换药，也不能把设备 Heat 指标或模型标签称为医生诊断。
5. normal 只能说“这次记录看起来比较平稳”或“出现正常窦性节律特征”，不能说没有心脏疾病。
不得把“正常窦性节律”解释为“身体健康”“心脏完全正常”或“心率一定正常”。可报告本次测得的心率数值并说明间隔是否均匀；只有确认测量时处于安静状态、且有适用年龄信息时，才可谨慎对照相应参考范围。一次短时心电记录不能评价整体健康。
6. atrial_fibrillation 只能说“出现与房颤相关的节律特征，建议复核”，不能说已经确诊房颤。
7. other_abnormality 只能说“存在其他异常节律可能”，不能猜测具体疾病名称。
8. too_noisy、signal_invalid、skipped_quality、model_uncertain、model_unavailable 或 unknown 时，
   必须先说明当前不能可靠分类，再给出复测动作；不能输出“正常”或“异常”的肯定结论。

三、三层表达方法
每次说明按以下顺序组织：
1. 结论层：先用一两句回答“这次能不能参考、是否需要复测”。
2. 解释层：说明分类或不确定的原因，只引用输入中的证据和数值。
3. 行动层：告诉用户现在怎么做，包括是否保存记录、如何调整测量、是否需要专业人员复核。
elderly_summary 必须像面对老人当面解释一样，短句、少术语、每句只表达一个重点。
建议使用“这次测量”“心跳节奏”“两次心跳之间的间隔”“信号里的干扰”等说法。
elderly_summary 禁止出现“单导联、窦性节律、RR、室性早搏、分类器、模型、信噪比、心电图、置信度”等术语。
不得用“您只是想多了”“肯定没事”等轻视或过度保证的话。
表达要像耐心聊天，不像宣读检查报告：可以自然地说“咱们先看这次记录”“您先别着急”，但不要每次都套同一句开场，也不要称呼“老爷爷/老奶奶”等可能显得冒犯的称呼。
先回应长辈最关心的事（结果能否参考、要不要重测），再解释一两个关键依据，最后告诉对方下一步怎么做。
安慰要承认感受但不替身体状况打包票；避免“放心，没事”“一切正常”。不确定时明确说“不确定不等于一定有问题”。
优先使用日常动作和具体时间，例如“坐着安静休息一会儿，再测一次”；不要只说“改善信号质量”或“注意观察”。

professional_interpretation 可以使用专业术语，但第一次出现时必须立即翻译：
“窦性节律（心跳节奏大体均匀，没有明显忽快忽慢）”“RR 间期不规则（两次心跳之间的间隔不均匀）”、
“QRS 波群增宽（心脏一次收缩时的电活动持续时间偏长）”。
如果没有对应证据，不要主动添加 P 波、QRS、QT、房颤或早搏等术语。

四、不同结果的写法
- signal_invalid / 质量不足：先说“这次没有录清楚，暂时不能判断”，再引用质量问题，
  给出坐稳、保持安静、清洁并贴紧电极、远离充电器、避免拉扯导线等具体动作。
- model_uncertain / 模型不可用：说明“信号可能可以记录，但当前没有足够可靠的分类结果”，
  不把模型未加载说成身体异常；建议复测或由专业人员查看。
- assistive_classification + normal：说明“本次记录看起来比较平稳”，可提心率，
  同时保留“短时记录只能作辅助参考”的限制。
- atrial_fibrillation：说明心跳间隔可能不规则，建议安静复测并尽快请专业人员复核，
  不把筛查提示写成诊断。
- other_abnormality：说明“存在需要进一步看的节律特征”，不猜具体疾病。

五、证据、数值和建议要求
1. evidence 最多3条，只能来自输入中的 concepts、quality、decision、flags 或 measurements。
   每条证据尽量包含“现象 + 来源数值/字段”，例如“记录中的心率为 77 次/分”。
2. 不把“模型说是正常”当作生理证据；分类结果和生理证据要分开表达。
3. confidence 低、quality 分数不足、存在 flags 或输入中有不确定性时，必须明确写出限制。
4. 心率必须保留“次/分”单位；不要把心率范围当作诊断标准。
5. next_steps 最多3条，按优先级排列；只允许复测、保存记录、咨询专业人员等安全建议。
6. measurement_guidance 只写可执行动作，每条尽量包含“怎么做”和“目的”，例如“坐稳并放松手臂，减少运动干扰”。
7. 如果 quality.issues 或 measurement_coach.actions 指出 baseline_drift（基线漂移），通俗说明应解释为波形基准线缓慢起伏，可能与身体移动、呼吸起伏或电极接触有关；不能据此推断心脏疾病。复测指导应温和地建议坐稳休息、放松手臂并有支撑、检查电极清洁干燥且贴合、避免拉扯导线后安静复测。不要要求屏住呼吸。
8. urgent_warning 不分析病因。若输入明确出现持续胸痛、明显胸闷、晕厥、呼吸困难等症状，
   直接建议立即联系当地急救服务或前往急诊；没有症状时也保留简短的症状提醒。
9. 语气安抚但不能保证安全：可以说“一次结果不确定并不等于一定有问题”，不能说“肯定没事”。

六、严格输出格式
只输出合法 JSON，不要 Markdown、不要代码块、不要额外解释。所有字段必须存在，数组没有内容时返回 []：
{
  "summary": "一句简短结论",
  "elderly_summary": "给老人看的两三句通俗结论",
  "professional_interpretation": "简短专业解释，并翻译首次出现的术语",
  "evidence": ["最多3条有输入依据的证据"],
  "uncertainty": ["至少1条限制或不确定性"],
  "reassurance": "一句温和、不过度保证的安抚",
  "advice": "一句概括性的安全建议",
  "symptom_questions": ["仅询问用户感受，不得假设症状存在"],
  "next_steps": ["最多3条下一步建议"],
  "measurement_guidance": ["需要复测时给出具体动作；不需要时返回空数组"],
  "urgent_warning": "出现哪些症状时需要及时就医",
  "risk_level": "reference_only | needs_review | repeat_measurement | urgent_symptoms",
  "diagnosis_status": "not_a_diagnosis"
}

risk_level 只能按以下规则填写：
- signal_invalid、信号不足、too_noisy、skipped_quality、model_uncertain 或 model_unavailable：repeat_measurement
- normal 且质量合格、decision.can_present_classification 为 true 且没有重要 flags：reference_only
- atrial_fibrillation、other_abnormality、unknown 或存在重要 flags：needs_review
- 只有输入明确包含紧急症状时：urgent_symptoms
"""


def _heart_rate_text(payload: dict[str, Any]) -> str:
    heart_rate = payload.get('measurements', {}).get('heart_rate') or {}
    bpm = heart_rate.get('bpm')
    if isinstance(bpm, (int, float)) and bpm > 0:
        return f'心跳大约每分钟 {bpm:g} 次'
    return '这次记录没有得到可靠的心率数值'


def _common_fields(labels: list[str], limitations: list[str]) -> dict[str, Any]:
    return {
        'evidence': labels[:3],
        'uncertainty': limitations[:2] or ['单导联短时记录只能提供辅助参考。'],
        'urgent_warning': '如果出现持续胸痛、明显胸闷、晕厥或呼吸困难，请立即联系当地急救服务或前往急诊。',
        'diagnosis_status': 'not_a_diagnosis',
        'provider': 'template',
        'api_called': False,
    }


def _symptom_questions(payload: dict[str, Any]) -> list[str]:
    classification = (payload.get('classification') or {}).get('label')
    concepts = payload.get('concepts') or []
    beats = (payload.get('measurements') or {}).get('beats') or {}
    has_ectopy_evidence = any(
        item.get('name') == 'ventricular_ectopy'
        for item in concepts
        if isinstance(item, dict)
    ) or (beats.get('vpc_count') or 0) > 0
    if has_ectopy_evidence:
        return [
            '测量前后有没有心慌、像漏跳一下或突然重重跳一下的感觉？',
            '有没有同时头晕、胸闷或气短？如果有，大约什么时候出现、持续了多久？',
        ]
    if classification in ('atrial_fibrillation', 'other_abnormality'):
        return [
            '最近有没有心慌、头晕、胸闷或气短？如果有，大约什么时候出现、持续了多久？',
        ]
    return []


def _ectopy_count(payload: dict[str, Any]) -> int:
    beats = (payload.get('measurements') or {}).get('beats') or {}
    count = beats.get('vpc_count') or 0
    if count:
        return int(count)
    for item in payload.get('concepts') or []:
        if isinstance(item, dict) and item.get('name') == 'ventricular_ectopy':
            return int((item.get('evidence') or {}).get('vpc_count') or 0)
    return 0


def _plain_summary_is_safe(summary: Any) -> bool:
    if not isinstance(summary, str) or not summary.strip():
        return False
    forbidden_terms = (
        '单导联',
        '窦性节律',
        'RR',
        '室性早搏',
        '分类器',
        '模型',
        '信噪比',
        '心电图',
    )
    return len(summary) <= 120 and not any(term in summary for term in forbidden_terms)


def _template(payload: dict[str, Any]) -> dict[str, Any]:
    classification = payload['classification'].get('label')
    concepts = payload.get('concepts', [])
    labels = [item['label'] for item in concepts]
    quality = payload.get('quality', {})
    limitations = payload.get('limitations', [])
    decision = payload.get('decision') or {}
    coach = payload.get('measurement_coach') or {}
    coach_actions = coach.get('actions') or []
    quality_issues = quality.get('issues') or []
    has_baseline_drift = any(
        issue.get('code') == 'baseline_drift'
        for issue in quality_issues
        if isinstance(issue, dict)
    ) or any('基线漂移' in str(reason) for reason in quality.get('reasons', []))
    baseline_guidance = [
        '坐稳休息，放松手臂并放在有支撑的位置，减少身体移动。',
        '检查电极接触处清洁、干燥并贴合，避免拉扯导线；正常呼吸，不必屏气。',
    ]
    measurements = payload.get('measurements') or {}
    heart_rate = measurements.get('heart_rate') or {}
    bpm = heart_rate.get('bpm')
    bpm_text = f'{bpm:g}' if isinstance(bpm, (int, float)) and bpm > 0 else '没有可靠数值'
    if decision.get('state') == 'model_uncertain':
        result = {
            'summary': '这次结果还不够确定，先不用紧张，建议按提示调整后重新测量。',
            'elderly_summary': (
                '这次波形的基准线有些慢慢起伏，可能和身体移动、呼吸起伏或电极接触有关，暂时不适合直接下结论。'
                '您先坐稳休息，放松手臂，检查电极贴合后再测一次；正常呼吸，不用屏气。'
                if has_baseline_drift
                else '这次信号里有一些干扰，或者模型把握不够大，所以不能把结果当成可靠判断。请先调整姿势和电极，再测一次。'
            ),
            'professional_interpretation': '当前结果进入模型不确定状态，暂不展示确定性的节律分类；需要结合更清晰的复测结果复核。',
            'risk_level': 'repeat_measurement',
            'advice': '请按照测量指导调整后重新采集，必要时由专业人员复核。',
            'reassurance': '模型不确定不等于身体一定有问题，先把信号录清楚更重要。',
            'next_steps': coach_actions[:3] or ['安静休息后重新测量。', '保存本次记录供后续对比。'],
            'measurement_guidance': baseline_guidance if has_baseline_drift else coach_actions[:3] or ['测量时保持安静和不动。'],
        }
        result.update(_common_fields(labels, limitations))
        result['symptom_questions'] = _symptom_questions(payload)
        return result
    if quality.get('status') == 'insufficient' or classification == 'too_noisy':
        result = {
            'summary': '这次记录的信号不够清楚，先不用紧张，但现在还不能可靠判断心跳情况。',
            'elderly_summary': '这次测量没有录清楚，不代表一定有问题。请坐好、放松，重新测一次。',
            'professional_interpretation': '由于信号质量不足，当前结果不进入节律分类。',
            'risk_level': 'repeat_measurement',
            'advice': '请保持安静并重新采集，必要时由专业人员复核。',
            'reassurance': '一次测量不清楚很常见，先调整姿势和电极，再测一次即可。',
            'next_steps': coach_actions[:3] or ['先坐下休息约1分钟。', '确认电极贴紧皮肤，测量时不要说话或移动。', '重新记录一段完整心电。'],
            'measurement_guidance': baseline_guidance if has_baseline_drift else coach_actions[:3] or ['手臂放松并保持不动。', '电极接触处保持清洁、干燥、贴合。'],
        }
        result.update(_common_fields(labels, limitations))
        result['symptom_questions'] = _symptom_questions(payload)
        return result

    heart_rate_text = _heart_rate_text(payload)
    if classification == 'normal':
        result = {
            'summary': f'这次记录显示心跳节奏较为均匀，{heart_rate_text}。这只是短时辅助结果。',
            'elderly_summary': f'这次记录里，心跳节奏看起来比较均匀，测到的心率约为每分钟 {bpm_text} 次。这个结果只能说明这段记录里的情况，不能单凭它判断身体整体是否健康。您可以先保存记录；如果有不舒服，请告诉家人并联系医生。',
            'professional_interpretation': '分类器将本次记录标记为正常窦性节律，也就是心跳节奏大体均匀，没有明显忽快忽慢。',
            'risk_level': 'reference_only',
            'advice': '建议保存记录，继续留意自己的身体感受；如有不舒服，请咨询专业人员。',
            'reassurance': '这次记录可以先作为参考，不必只因为这一个结果过分担心；它不能代替医生的判断。',
            'next_steps': ['保存本次记录，方便以后对比。', '按需要在安静状态下继续记录。', '如出现明显不适，及时咨询专业人员。'],
            'measurement_guidance': [],
        }
    elif classification == 'atrial_fibrillation':
        result = {
            'summary': f'这次记录出现房颤相关特征，{heart_rate_text}。这不是确诊，请先复测并请专业人员复核。',
            'elderly_summary': f'这次记录里，心跳之间的间隔看起来可能不太均匀，{heart_rate_text}。这只是提醒进一步核对，不等于已经确诊。请先保存记录，按指导安静复测；药物请照医生原来的安排使用。',
            'professional_interpretation': '模型发现与房颤相关的节律特征，例如 RR 间期不规则；单导联短时记录仍需要结合复测和专业检查确认。',
            'risk_level': 'needs_review',
            'advice': '建议保存记录并尽快咨询专业人员，结合症状和后续心电记录判断。',
            'reassurance': '先不要因为一次提示就过度害怕，复测和专业复核可以帮助确认情况。',
            'next_steps': ['安静休息后重新测量一次。', '保存本次和后续记录。', '尽快把记录交给专业人员查看。'],
            'measurement_guidance': ['测量时保持坐姿、安静，不要说话或移动。'],
        }
    elif classification == 'other_abnormality':
        ectopy_count = _ectopy_count(payload)
        elderly_summary = (
            f'这次记录整体节奏比较平稳，但看到 {ectopy_count} 次心跳比前后稍早出现。'
            '这只是需要进一步核对的线索，不等于确诊。您当时有没有心慌、像漏跳一下、头晕或胸闷？'
            '可以安静休息后复测，并把记录保存下来给医生看。'
            if ectopy_count > 0
            else f'这次记录里有些节奏需要再核对，{heart_rate_text}。单凭这一小段记录还不能判断是什么原因。您可以先休息后再测一次，并把记录带给医生看。'
        )
        result = {
            'summary': f'这次记录出现需要进一步看的节律特征，{heart_rate_text}。目前不能仅凭这次记录判断具体疾病。',
            'elderly_summary': elderly_summary,
            'professional_interpretation': '模型标记为其他异常节律可能，说明记录中存在需要复核的特征，但当前单导联结果不能确定具体诊断。',
            'risk_level': 'needs_review',
            'advice': '建议复测并由专业人员结合完整心电图、症状和既往情况判断。',
            'reassurance': '这不是诊断结论，很多因素都可能影响一次短时记录，先复测会更有帮助。',
            'next_steps': ['休息后重新测量。', '保存异常记录和测量时间。', '携带记录咨询专业人员。'],
            'measurement_guidance': ['确保电极贴合，测量期间保持不动。'],
        }
    else:
        result = {
            'summary': '这次记录暂时无法给出明确的辅助分类，请重新测量。',
            'elderly_summary': '这次结果还不够确定，先不用紧张。请按正确姿势重新测量，再看看结果。',
            'professional_interpretation': '当前模型输出未知或未完成，不能据此作出节律判断。',
            'risk_level': 'repeat_measurement',
            'advice': '请重新采集，仍然不确定时咨询专业人员。',
            'reassurance': '一次结果不确定并不等于有疾病，先把信号录清楚更重要。',
            'next_steps': ['安静休息后重新测量。', '确认电极接触良好。', '如多次不确定，请咨询专业人员。'],
            'measurement_guidance': ['保持安静和不动，避免说话、抖动和拉扯导线。'],
        }
    result.update(_common_fields(labels, limitations))
    result['symptom_questions'] = _symptom_questions(payload)
    return result


def _llm(payload: dict[str, Any]) -> dict[str, Any]:
    provider = os.environ.get('ECG_EXPLANATION_PROVIDER', 'template')
    endpoint = os.environ.get('ECG_LLM_ENDPOINT')
    if not endpoint and provider == 'deepseek':
        endpoint = 'https://api.deepseek.com'
    if not endpoint:
        raise RuntimeError('ECG_LLM_ENDPOINT 未配置')
    endpoint = endpoint.rstrip('/') + '/chat/completions'
    body = {
        'model': os.environ.get(
            'ECG_LLM_MODEL',
            'deepseek-chat' if provider == 'deepseek' else 'qwen',
        ),
        'temperature': 0.1,
        'response_format': {'type': 'json_object'},
        'messages': [
            {'role': 'system', 'content': (
                EXPLANATION_SYSTEM_PROMPT
            )},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
        ],
    }
    headers = {'Content-Type': 'application/json'}
    api_key = os.environ.get('DEEPSEEK_API_KEY') if provider == 'deepseek' else os.environ.get('ECG_LLM_API_KEY')
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    req = request.Request(endpoint, data=json.dumps(body).encode('utf-8'), headers=headers, method='POST')
    with request.urlopen(req, timeout=float(os.environ.get('ECG_LLM_TIMEOUT', '10'))) as response:
        content = json.loads(response.read().decode('utf-8'))
    return json.loads(content['choices'][0]['message']['content'])


def generate_explanation(payload: dict[str, Any]) -> dict[str, Any]:
    load_project_env()
    if os.environ.get('ECG_EXPLANATION_PROVIDER') in ('openai_compatible', 'deepseek'):
        try:
            result = _llm(payload)
            template = _template(payload)
            for key, value in template.items():
                result.setdefault(key, value)
            if not _plain_summary_is_safe(result.get('elderly_summary')):
                result['elderly_summary'] = template['elderly_summary']
            result['diagnosis_status'] = 'not_a_diagnosis'
            result['symptom_questions'] = template['symptom_questions']
            result['provider'] = os.environ.get('ECG_EXPLANATION_PROVIDER')
            result['api_called'] = True
            return result
        except Exception as exc:
            result = _template(payload)
            result['fallback_reason'] = f'{type(exc).__name__}: {exc}'
            return result
    result = _template(payload)
    result['fallback_reason'] = 'ECG_EXPLANATION_PROVIDER 未设置为 deepseek 或 openai_compatible'
    return result
