"""Template-first ECG explanation with optional OpenAI-compatible LLM support."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib import request


EXPLANATION_SYSTEM_PROMPT = """你是“未卜心知”的心电辅助说明助手。
你的表达要像一位温和、耐心、专业的家庭健康顾问：第一部分必须先用两三句日常语言总结“这次看到了什么、是否需要复测或复核、现在该做什么”，让不懂医学的老人也能立即听明白；之后再补充专业依据。
不要声称自己是真实医生，不要把模型结果包装成确诊。

输入是单导联短时心电分析结果。你只能解释输入中已有的分类、概念、测量值和质量信息，
不能凭空增加疾病、症状、药物、检查结果或治疗方案。

必须遵守：
1. diagnosis_status 固定为 "not_a_diagnosis"。
2. 禁止使用“确诊、排除、一定是、一定不是、完全正常、没有任何问题”等绝对表述。
3. normal 只能说“这次记录看起来比较平稳/呈正常窦性节律特征”，不能说没有心脏疾病。
4. atrial_fibrillation 只能说“出现房颤相关特征，建议复核”，不能说已经确诊房颤。
5. other_abnormality 只能说“存在其他异常节律可能”，不能猜测具体疾病。
6. too_noisy、信号质量不足、模型未完成或 unknown 时，必须先说明无法可靠判断，并指导重新测量。
7. 所有专业术语后面立即用通俗话解释，例如“窦性节律（心跳节奏总体规则）”。
8. evidence 只能引用输入中的事实；不要编造数值，不要把推测写成事实。
9. confidence 较低、存在冲突标记或模型异常时，要明确说明不确定。
10. 建议只能包括保持安静、重新贴好电极、重新测量、保存记录、咨询专业人员等。
11. 如果输入包含胸痛、胸闷、晕厥、呼吸困难等紧急症状，只提醒立即联系当地急救服务或就近急诊，不分析病因。
12. 语气安抚但不能保证安全；不要因为安抚而淡化异常结果。
13. 对输入中实际出现的异常类别，可补充一般医学知识：定义、可能伴随的感受、常见相关因素和需要及时就医的情况。
14. 必须使用“可能、可见于、部分人会”等条件表达，明确这些知识不表示本次用户已经出现相应症状或病因。
15. 不得根据心拍类别推断冠心病、心肌炎、电解质异常、药物影响等具体病因；只能列为一般相关因素并建议专业评估。
16. 不得在没有质量证据时声称“采集时动了、电极没贴好、异常是干扰假象”。只有 quality.warnings、reason_codes、bSQI 或状态帧明确支持时，才能说明对应干扰。
17. 即使存在噪声，也不能直接否定 PAC、PVC 或融合心拍；应表述为“结果可能受信号质量影响，需要复测或结合原始波形复核”。
18. 通俗总结优先使用自然叙述：记录时长与总心拍、平均心率和规则性、各异常类别数量、是否需要复测或复核。避免逐字段复述JSON。
19. 当 quality.status 为 basic_checks_passed、bSQI 较高且没有电极或运动相关 warning/reason 时，不要建议重新贴电极，也不要声称采集不稳；可以建议在相同条件下复测以确认重复性。

只输出严格 JSON，不要 Markdown，字段必须完整：
{
  "elderly_summary": "必须放在最前面的两三句通俗总结：本次主要发现、需要担心到什么程度、下一步怎么做；避免术语和类别代码",
  "professional_interpretation": "简短专业解释，并翻译术语",
  "condition_education": [{"condition": "输入中出现的异常", "what_it_means": "通俗定义", "possible_symptoms": ["一般可能伴随的感受"], "common_associations": ["一般常见相关因素"], "when_to_seek_care": ["需要及时就医的情况"], "not_patient_facts": true}],
  "evidence": ["最多3条输入中有依据的证据"],
  "uncertainty": ["至少1条限制或不确定性"],
  "reassurance": "一句温和、不过度保证的安抚",
  "next_steps": ["最多3条下一步建议"],
  "measurement_guidance": ["需要复测时给出动作；不需要时返回空数组"],
  "urgent_warning": "出现哪些症状时需要及时就医",
  "risk_level": "reference_only | needs_review | repeat_measurement | urgent_symptoms",
  "diagnosis_status": "not_a_diagnosis"
}

risk_level 规则：
- 信号不足、too_noisy 或模型未完成：repeat_measurement
- normal 且没有重要风险标记：reference_only
- atrial_fibrillation、other_abnormality、unknown 或有重要 flags：needs_review
- 只有输入明确出现紧急症状时：urgent_symptoms
"""

REQUIRED_FIELDS = {
    'elderly_summary': str,
    'professional_interpretation': str,
    'condition_education': list,
    'evidence': list,
    'uncertainty': list,
    'reassurance': str,
    'next_steps': list,
    'measurement_guidance': list,
    'urgent_warning': str,
    'risk_level': str,
    'diagnosis_status': str,
}
RISK_LEVELS = {'reference_only', 'needs_review', 'repeat_measurement', 'urgent_symptoms'}


def _load_project_env() -> None:
    """Load explanation settings from project .env without overriding process env."""
    env_file = Path(__file__).resolve().parents[2] / '.env'
    try:
        lines = env_file.read_text(encoding='utf-8').splitlines()
    except OSError:
        return
    allowed = {
        'ECG_EXPLANATION_PROVIDER', 'ECG_LLM_ENDPOINT', 'ECG_LLM_MODEL',
        'ECG_LLM_TIMEOUT', 'ECG_LLM_API_KEY', 'DEEPSEEK_API_KEY',
    }
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        key, separator, value = stripped.partition('=')
        key = key.strip()
        if separator and key in allowed and key not in os.environ:
            os.environ[key] = value.strip().strip('\"').strip("'")


def _validate_llm_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError('大模型返回值不是 JSON 对象')
    for field, expected in REQUIRED_FIELDS.items():
        if not isinstance(result.get(field), expected):
            raise ValueError(f'大模型返回字段 {field} 缺失或类型错误')
    if result['diagnosis_status'] != 'not_a_diagnosis':
        raise ValueError('大模型违反 diagnosis_status 安全约束')
    if result['risk_level'] not in RISK_LEVELS:
        raise ValueError('大模型返回未知 risk_level')
    for field in ('evidence', 'uncertainty', 'next_steps', 'measurement_guidance'):
        if not all(isinstance(item, str) for item in result[field]):
            raise ValueError(f'大模型返回字段 {field} 必须是字符串数组')
    result['evidence'] = result['evidence'][:3]
    result['uncertainty'] = result['uncertainty'][:3]
    result['next_steps'] = result['next_steps'][:3]
    result['measurement_guidance'] = result['measurement_guidance'][:3]
    for item in result['condition_education']:
        if not isinstance(item, dict) or not isinstance(item.get('condition'), str):
            raise ValueError('condition_education 项目格式错误')
        for field in ('what_it_means',):
            if not isinstance(item.get(field), str):
                raise ValueError(f'condition_education.{field} 类型错误')
        for field in ('possible_symptoms', 'common_associations', 'when_to_seek_care'):
            if not isinstance(item.get(field), list) or not all(isinstance(value, str) for value in item[field]):
                raise ValueError(f'condition_education.{field} 必须是字符串数组')
            item[field] = item[field][:4]
        item['not_patient_facts'] = True
    result['condition_education'] = result['condition_education'][:6]
    return result


EDUCATION = {
    'pac': {
        'condition': '室上性早搏（PAC/S类心拍）',
        'what_it_means': '心房或房室交界区提前发出一次心跳信号，形成比预期更早的心拍。',
        'possible_symptoms': ['部分人没有感觉', '可能感到心跳漏一拍、突然一跳或短暂心悸'],
        'common_associations': ['疲劳、紧张、睡眠不足', '咖啡因、酒精或吸烟', '也可见于某些心脏或全身状况，需结合临床评估'],
        'when_to_seek_care': ['反复或持续出现并伴明显不适时咨询专业人员', '伴胸痛、晕厥或呼吸困难时及时就医'],
    },
    'pvc': {
        'condition': '室性早搏（PVC/V类心拍）',
        'what_it_means': '心室提前产生一次电活动，心拍形态可能与多数正常心拍不同。',
        'possible_symptoms': ['部分人没有感觉', '可能感到心跳重、停顿感、漏跳感或心悸', '频繁时部分人可能感到乏力或头晕'],
        'common_associations': ['疲劳、压力、睡眠不足', '咖啡因、酒精、吸烟或部分药物', '也可与电解质、甲状腺或心脏结构问题等相关，但本记录不能判断原因'],
        'when_to_seek_care': ['新出现、明显增多或持续成串时建议专业复核', '伴胸痛、晕厥、明显气短或持续心动过速时及时就医'],
    },
    'fusion': {
        'condition': '融合心拍（F类心拍）',
        'what_it_means': '一次正常传导与一次室性激动几乎同时到达心室，形成混合形态的心拍。',
        'possible_symptoms': ['可能没有明显感觉', '也可能伴随心悸或心跳不规则感'],
        'common_associations': ['可在存在室性异位活动时出现', '单导联模型也可能把噪声或形态变化误分为融合心拍'],
        'when_to_seek_care': ['重复记录仍出现时建议结合十二导联心电图复核', '伴明显不适或紧急症状时及时就医'],
    },
    'atrial_fibrillation': {
        'condition': '房颤相关节律特征',
        'what_it_means': '心房电活动可能快速而不规则，使心室节律呈不规则特征；当前结果不能替代临床确诊。',
        'possible_symptoms': ['可能没有症状', '可能出现心悸、乏力、头晕、胸闷或活动后气短'],
        'common_associations': ['年龄增长、高血压和部分心脏疾病', '甲状腺、酒精、感染等因素也可能相关，但不能由本记录确定'],
        'when_to_seek_care': ['首次出现相关提示时建议尽快专业复核', '伴胸痛、晕厥、严重呼吸困难或神经功能异常时立即就医'],
    },
    'fast_rate': {
        'condition': '心率偏快', 'what_it_means': '本次记录的平均心率高于展示阈值。',
        'possible_symptoms': ['可能心悸、胸闷、气短、头晕，也可能无明显感觉'],
        'common_associations': ['运动、紧张、发热、脱水', '贫血、甲状腺或心律问题等也可能相关'],
        'when_to_seek_care': ['静息时持续偏快或伴明显不适时咨询专业人员', '伴胸痛、晕厥或严重气短时及时就医'],
    },
    'slow_rate': {
        'condition': '心率偏慢', 'what_it_means': '本次记录的平均心率低于展示阈值。',
        'possible_symptoms': ['可能没有症状', '部分人可能乏力、头晕、活动耐量下降或接近晕厥'],
        'common_associations': ['睡眠、运动训练状态', '部分药物或传导系统问题等也可能相关'],
        'when_to_seek_care': ['反复偏慢并伴不适时咨询专业人员', '出现晕厥、胸痛或呼吸困难时及时就医'],
    },
}


def _condition_education(payload: dict[str, Any]) -> list[dict[str, Any]]:
    keys: list[str] = []
    beat = payload.get('beat_analysis') or payload.get('analysis_scope', {}).get('beat_analysis') or {}
    counts = beat.get('counts') or {}
    for key in ('pac', 'pvc', 'fusion'):
        if isinstance(counts.get(key), (int, float)) and counts[key] > 0:
            keys.append(key)
    rhythm = payload.get('rhythm_analysis') or payload.get('analysis_scope', {}).get('rhythm_analysis') or {}
    if rhythm.get('primary') == 'atrial_fibrillation' or payload.get('classification', {}).get('label') == 'atrial_fibrillation':
        keys.append('atrial_fibrillation')
    rate = payload.get('rate_analysis') or payload.get('analysis_scope', {}).get('rate_analysis') or {}
    if rate.get('result') == 'high': keys.append('fast_rate')
    if rate.get('result') == 'low': keys.append('slow_rate')
    return [{**EDUCATION[key], 'not_patient_facts': True} for key in dict.fromkeys(keys)]


def _heart_rate_text(payload: dict[str, Any]) -> str:
    heart_rate = payload.get('measurements', {}).get('heart_rate') or {}
    bpm = heart_rate.get('bpm')
    if isinstance(bpm, (int, float)) and bpm > 0:
        return f'心跳大约每分钟 {bpm:g} 次'
    return '这次记录没有得到可靠的心率数值'


def _plain_beat_summary(payload: dict[str, Any]) -> str | None:
    beat = payload.get('beat_analysis') or payload.get('analysis_scope', {}).get('beat_analysis') or {}
    counts = beat.get('counts') or {}
    total = beat.get('total')
    if not isinstance(total, (int, float)):
        total = sum(value for value in counts.values() if isinstance(value, (int, float)))
    rate = payload.get('rate_analysis') or payload.get('analysis_scope', {}).get('rate_analysis') or {}
    bpm = rate.get('average_bpm')
    if not isinstance(total, (int, float)) or total <= 0:
        return None
    parts = [f'本次记录共识别到 {int(total)} 个心拍']
    if isinstance(bpm, (int, float)):
        parts.append(f'平均心率约 {bpm:g} 次/分')
    if rate.get('regularity') == 'regular':
        parts.append('整体节奏相对规则')
    elif rate.get('regularity') == 'irregular':
        parts.append('心跳间隔存在不规则特征')
    detail = []
    if counts.get('normal'): detail.append(f"正常类 {int(counts['normal'])} 拍")
    if counts.get('pac'): detail.append(f"室上性提前心拍候选 {int(counts['pac'])} 拍")
    if counts.get('pvc'): detail.append(f"室性提前心拍候选 {int(counts['pvc'])} 拍")
    if counts.get('fusion'): detail.append(f"融合心拍候选 {int(counts['fusion'])} 拍")
    sentence = '，'.join(parts) + '。'
    if detail:
        sentence += '模型逐拍结果包括' + '、'.join(detail) + '。'
    sentence += '这些结果用于辅助参考，不能单独作为诊断；异常心拍较多或伴有不适时，建议保存记录并请专业人员复核。'
    return sentence


def _common_fields(labels: list[str], limitations: list[str]) -> dict[str, Any]:
    return {
        'evidence': labels[:3],
        'uncertainty': limitations[:2] or ['单导联短时记录只能提供辅助参考。'],
        'urgent_warning': '如果出现持续胸痛、明显胸闷、晕厥或呼吸困难，请立即联系当地急救服务或前往急诊。',
        'diagnosis_status': 'not_a_diagnosis',
        'provider': 'template',
        'api_called': False,
        'condition_education': [],
    }


def _template(payload: dict[str, Any]) -> dict[str, Any]:
    classification = payload['classification'].get('label')
    concepts = payload.get('concepts', [])
    labels = [item['label'] for item in concepts]
    quality = payload.get('quality', {})
    limitations = payload.get('limitations', [])
    education = _condition_education(payload)
    if quality.get('status') == 'insufficient' or classification == 'too_noisy':
        result = {
            'summary': '这次记录的信号不够清楚，先不用紧张，但现在还不能可靠判断心跳情况。',
            'elderly_summary': '这次测量没有录清楚，不代表一定有问题。请坐好、放松，重新测一次。',
            'professional_interpretation': '由于信号质量不足，当前结果不进入节律分类。',
            'risk_level': 'repeat_measurement',
            'advice': '请保持安静并重新采集，必要时由专业人员复核。',
            'reassurance': '一次测量不清楚很常见，先调整姿势和电极，再测一次即可。',
            'next_steps': ['先坐下休息约1分钟。', '确认电极贴紧皮肤，测量时不要说话或移动。', '重新记录一段完整心电。'],
            'measurement_guidance': ['手臂放松并保持不动。', '电极接触处保持清洁、干燥、贴合。'],
        }
        result.update(_common_fields(labels, limitations))
        result['condition_education'] = education
        return result

    heart_rate_text = _heart_rate_text(payload)
    if payload['classification'].get('task_type') == 'beat_level' and classification:
        plain_summary = _plain_beat_summary(payload)
        result = {
            'summary': f'本次逐拍分类：{classification}。{heart_rate_text}。',
            'elderly_summary': plain_summary or f'本次记录已完成逐拍分析。请保存记录作为复核参考。',
            'professional_interpretation': 'CNN为N/S/V/F四类；HGB为N/S/VF三类。N类不代表健康，VF是V/E/F合并，不是心室颤动。',
            'risk_level': 'needs_review', 'advice': '结果用于课程研究，请结合原始波形复核。',
            'next_steps': ['保存本次记录。', '有不适时请由专业人员复核。'],
            'measurement_guidance': [], 'reassurance': '模型类别是辅助信息，不能直接作出疾病诊断。',
        }
        result.update(_common_fields(labels, limitations))
        result['condition_education'] = education
        return result
    if classification == 'normal':
        result = {
            'summary': f'这次记录看起来比较平稳，{heart_rate_text}。先不用过度紧张。',
            'elderly_summary': f'从这次记录看，心跳节奏总体比较规则，{heart_rate_text}。目前没有看到需要立刻处理的明显提示。',
            'professional_interpretation': '分类器将本次记录标记为正常窦性节律，也就是心跳节奏总体由心脏正常起搏点带动。',
            'risk_level': 'reference_only',
            'advice': '建议保存记录，继续留意自己的身体感受；如有不舒服，请咨询专业人员。',
            'reassurance': '目前这条记录可以先作为相对安心的参考，但它不能代替完整心电图和医生判断。',
            'next_steps': ['保存本次记录，方便以后对比。', '按需要在安静状态下继续记录。', '如出现明显不适，及时咨询专业人员。'],
            'measurement_guidance': [],
        }
    elif classification == 'atrial_fibrillation':
        result = {
            'summary': f'这次记录出现房颤相关特征，{heart_rate_text}。这不是确诊，请先复测并请专业人员复核。',
            'elderly_summary': f'这次心电记录提示心跳节奏可能不太规则，{heart_rate_text}。这只是辅助筛查，不等于已经确诊房颤，请不要自行停药或加药。',
            'professional_interpretation': '模型发现与房颤相关的节律特征，例如 RR 间期不规则；单导联短时记录仍需要结合复测和专业检查确认。',
            'risk_level': 'needs_review',
            'advice': '建议保存记录并尽快咨询专业人员，结合症状和后续心电记录判断。',
            'reassurance': '先不要因为一次提示就过度害怕，复测和专业复核可以帮助确认情况。',
            'next_steps': ['安静休息后重新测量一次。', '保存本次和后续记录。', '尽快把记录交给专业人员查看。'],
            'measurement_guidance': ['测量时保持坐姿、安静，不要说话或移动。'],
        }
    elif classification == 'other_abnormality':
        result = {
            'summary': f'这次记录出现需要进一步看的节律特征，{heart_rate_text}。目前不能仅凭这次记录判断具体疾病。',
            'elderly_summary': f'这次记录和常见的规则节奏不完全一样，但还不能据此判断是什么病，{heart_rate_text}。请先复测并带着记录咨询专业人员。',
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
    result['condition_education'] = education
    return result


def _llm(payload: dict[str, Any]) -> dict[str, Any]:
    _load_project_env()
    provider = os.environ.get('ECG_EXPLANATION_PROVIDER', 'template')
    endpoint = os.environ.get('ECG_LLM_ENDPOINT')
    if not endpoint and provider == 'deepseek':
        endpoint = 'https://api.deepseek.com'
    if not endpoint:
        raise RuntimeError('ECG_LLM_ENDPOINT 未配置')
    endpoint = endpoint.rstrip('/') + '/chat/completions'
    model = os.environ.get(
        'ECG_LLM_MODEL',
        'deepseek-chat' if provider == 'deepseek' else 'qwen',
    )
    body = {
        'model': model,
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
    started = time.perf_counter()
    with request.urlopen(req, timeout=float(os.environ.get('ECG_LLM_TIMEOUT', '10'))) as response:
        content = json.loads(response.read().decode('utf-8'))
    result = _validate_llm_result(json.loads(content['choices'][0]['message']['content']))
    result['provider'] = provider
    result['model'] = model
    result['api_called'] = True
    result['latency_ms'] = round((time.perf_counter() - started) * 1000, 1)
    return result


def generate_explanation(payload: dict[str, Any]) -> dict[str, Any]:
    _load_project_env()
    if os.environ.get('ECG_EXPLANATION_PROVIDER') in ('openai_compatible', 'deepseek'):
        try:
            result = _llm(payload)
            template = _template(payload)
            for key, value in template.items():
                result.setdefault(key, value)
            result['diagnosis_status'] = 'not_a_diagnosis'
            return result
        except Exception as exc:
            result = _template(payload)
            result['fallback_reason'] = f'{type(exc).__name__}: {exc}'
            return result
    result = _template(payload)
    result['fallback_reason'] = 'ECG_EXPLANATION_PROVIDER 未设置为 deepseek 或 openai_compatible'
    return result
