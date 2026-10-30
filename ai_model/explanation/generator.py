"""Template-first ECG explanation with optional OpenAI-compatible LLM support."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib import request


EXPLANATION_SYSTEM_PROMPT = """你是“未卜心知”的心电辅助说明助手。
你的表达要像一位温和、耐心、专业的家庭健康顾问：先让不懂医学的老年人听明白，再补充必要的专业依据。
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

只输出严格 JSON，不要 Markdown，字段必须完整：
{
  "elderly_summary": "给老人看的两三句通俗结论",
  "professional_interpretation": "简短专业解释，并翻译术语",
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


def _template(payload: dict[str, Any]) -> dict[str, Any]:
    classification = payload['classification'].get('label')
    concepts = payload.get('concepts', [])
    labels = [item['label'] for item in concepts]
    quality = payload.get('quality', {})
    limitations = payload.get('limitations', [])
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
        return result

    heart_rate_text = _heart_rate_text(payload)
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
    if os.environ.get('ECG_EXPLANATION_PROVIDER') in ('openai_compatible', 'deepseek'):
        try:
            result = _llm(payload)
            template = _template(payload)
            for key, value in template.items():
                result.setdefault(key, value)
            result['diagnosis_status'] = 'not_a_diagnosis'
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
