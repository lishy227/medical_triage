"""
RAG检索模块 - 基于 medical.json 的疾病知识检索（支持 MySQL / JSON 双后端）
"""
import json
import os
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, inspect


@dataclass
class RetrievedDisease:
    """检索到的疾病结果"""
    name: str
    score: float  # 相似度分数
    disease: Any  # Disease对象
    matched_symptoms: List[str]  # 匹配的症状


class DiseaseRAGRetriever:
    """
    疾病知识RAG检索器
    
    使用简单关键词匹配 + 向量检索（后续可升级）
    """
    
    def __init__(self, knowledge_base=None):
        """
        初始化检索器
        
        Args:
            knowledge_base: MedicalKnowledgeBase实例，为None时自动加载
        """
        if knowledge_base is None:
            from knowledge_base.loader import load_knowledge_base
            self.kb = load_knowledge_base()
        else:
            self.kb = knowledge_base
        
        # 构建症状倒排索引
        self._symptom_index: Dict[str, List[Any]] = {}
        self._build_index()
    
    def _build_index(self):
        """构建症状倒排索引"""
        print("构建症状索引...")
        for disease in self.kb.diseases:
            for symptom in disease.symptom:
                symptom = symptom.strip()
                if symptom not in self._symptom_index:
                    self._symptom_index[symptom] = []
                self._symptom_index[symptom].append(disease)
        print(f"索引构建完成，共 {len(self._symptom_index)} 个症状条目")
    
    def retrieve(
        self, 
        symptoms: List[str], 
        body_part: Optional[str] = None,
        top_k: int = 5
    ) -> List[RetrievedDisease]:
        """
        检索相关疾病
        
        Args:
            symptoms: 用户症状列表
            body_part: 身体部位（可选，用于过滤）
            top_k: 返回最相关的K个疾病
            
        Returns:
            检索到的疾病列表
        """
        # 计算每个疾病的匹配分数
        disease_scores: Dict[str, Tuple[float, Any, List[str]]] = {}
        
        for symptom in symptoms:
            symptom = symptom.strip()
            # 模糊匹配症状
            matched_diseases = self._fuzzy_match_symptom(symptom)
            
            for disease, match_score in matched_diseases:
                if disease.name not in disease_scores:
                    disease_scores[disease.name] = [0.0, disease, []]
                
                disease_scores[disease.name][0] += match_score
                if symptom not in disease_scores[disease.name][2]:
                    disease_scores[disease.name][2].append(symptom)
        
        # 按分数排序
        sorted_diseases = sorted(
            disease_scores.items(),
            key=lambda x: x[1][0],
            reverse=True
        )
        
        # 转换为结果对象
        results = []
        for name, (score, disease, matched) in sorted_diseases[:top_k]:
            # 归一化分数
            normalized_score = min(score / len(symptoms), 1.0)
            results.append(RetrievedDisease(
                name=name,
                score=normalized_score,
                disease=disease,
                matched_symptoms=matched
            ))
        
        return results
    
    def _fuzzy_match_symptom(self, symptom: str) -> List[Tuple[Any, float]]:
        """
        模糊匹配症状
        
        Returns:
            [(disease, score), ...]
        """
        results = []
        matched_diseases = set()
        
        # 1. 精确匹配
        if symptom in self._symptom_index:
            for disease in self._symptom_index[symptom]:
                if disease.name not in matched_diseases:
                    results.append((disease, 1.0))
                    matched_diseases.add(disease.name)
        
        # 2. 包含匹配（症状包含关键词）
        for indexed_symptom, diseases in self._symptom_index.items():
            if symptom in indexed_symptom or indexed_symptom in symptom:
                for disease in diseases:
                    if disease.name not in matched_diseases:
                        results.append((disease, 0.7))
                        matched_diseases.add(disease.name)
        
        return results
    
    def get_disease_detail(self, disease_name: str) -> Optional[Any]:
        """获取疾病详情"""
        return self.kb.get_by_name(disease_name)


class DiseaseExplanationGenerator:
    """
    疾病解释生成器
    
    基于检索结果生成用户友好的解释和建议
    """
    
    def __init__(self, retriever: DiseaseRAGRetriever):
        self.retriever = retriever
    
    def generate_explanation(
        self,
        user_symptoms: List[str],
        body_part: Optional[str] = None,
        top_disease: Optional[RetrievedDisease] = None
    ) -> Dict[str, Any]:
        """
        生成疾病解释和建议
        
        Args:
            user_symptoms: 用户症状
            body_part: 身体部位
            top_disease: 最可能的疾病（如已确定）
            
        Returns:
            包含解释和建议的字典
        """
        # 如果没有指定疾病，先检索
        if top_disease is None:
            retrieved = self.retriever.retrieve(user_symptoms, body_part, top_k=1)
            if not retrieved:
                return self._generate_fallback_response(user_symptoms)
            top_disease = retrieved[0]
        
        disease = top_disease.disease
        
        # 构建解释
        explanation = {
            "disease_name": disease.name,
            "match_score": round(top_disease.score * 80, 1),
            "matched_symptoms": top_disease.matched_symptoms,
            
            # 疾病解释
            "description": self._format_description(disease.desc),
            "cause": self._format_cause(disease.cause),
            
            # 科室推荐
            "departments": disease.cure_department,
            
            # 建议检查
            "recommended_checks": disease.check[:5] if disease.check else [],
            
            # 治疗方式
            "treatment_methods": disease.cure_way,
            "treatment_duration": disease.cure_lasttime,
            "cure_probability": disease.cured_prob,
            
            # 常用药物
            "common_drugs": disease.common_drug[:5] if disease.common_drug else [],
            
            # 饮食建议
            "recommended_foods": disease.do_eat[:5] if disease.do_eat else [],
            "avoid_foods": disease.not_eat[:5] if disease.not_eat else [],
            
            # 预防建议
            "prevention": self._format_prevention(disease.prevent),
            
            # 注意事项
            "notes": self._generate_notes(disease)
        }
        
        return explanation
    
    def generate_enhanced_response(
        self,
        user_symptoms: List[str],
        body_part: Optional[str] = None,
        department_recommendation: Optional[List[str]] = None
    ) -> str:
        """
        生成增强的回复文本（用于直接展示给用户）
        
        Args:
            user_symptoms: 用户症状
            body_part: 身体部位
            department_recommendation: 原有系统推荐的科室
            
        Returns:
            格式化的回复文本
        """
        # 检索相关疾病
        retrieved = self.retriever.retrieve(user_symptoms, body_part, top_k=3)
        
        if not retrieved:
            return self._generate_simple_response(user_symptoms, department_recommendation)
        
        top_disease = retrieved[0]
        exp = self.generate_explanation(user_symptoms, body_part, top_disease)
        
        # 构建回复
        lines = []
        
        # 1. 匹配结果
        lines.append(f"根据您描述的{'、'.join(user_symptoms)}等症状，")
        lines.append(f"可能与 **{exp['disease_name']}** 相关（匹配度：{exp['match_score']}%）")
        lines.append("")
        
        # 2. 疾病简介
        if exp['description']:
            lines.append("")
            lines.append(f"📋 **疾病简介**")
            lines.append(exp['description'])
            lines.append("")
        
        # 3. 科室推荐
        if department_recommendation:
            lines.append("")
            lines.append(f"🏥 **推荐科室**：{', '.join(department_recommendation)}")
        elif exp['departments']:
            lines.append("")
            lines.append(f"🏥 **推荐科室**：{', '.join(exp['departments'])}")
        lines.append("")
        
        # 4. 建议检查
        if exp['recommended_checks']:
            lines.append("")
            lines.append(f"📝 **建议检查**：{', '.join(exp['recommended_checks'])}")
            lines.append("")
        
        # 5. 治疗方式
        if exp['treatment_methods']:
            lines.append("")
            lines.append(f"💊 **治疗方式**：{', '.join(exp['treatment_methods'])}")
            if exp['treatment_duration']:
                lines.append("\n")
                lines.append(f"⏱️ **治疗周期**：{exp['treatment_duration']}")
            if exp['cure_probability']:
                lines.append("\n")
                lines.append(f"📊 **治愈概率**：{exp['cure_probability']}")
        
        # 6. 常用药物
        if exp['common_drugs']:
            lines.append("")
            lines.append(f"💉 **参考药物**：{', '.join(exp['common_drugs'])}")
            lines.append("（具体用药请遵医嘱）")
        
        # 7. 饮食建议
        if exp['recommended_foods'] or exp['avoid_foods']:
            lines.append("")
            lines.append(f"🍎 **饮食建议**")
            if exp['recommended_foods']:
                lines.append(f"   宜吃：{', '.join(exp['recommended_foods'])}")
            if exp['avoid_foods']:
                lines.append(f"   忌吃：{', '.join(exp['avoid_foods'])}")
        
        # 8. 预防建议
        if exp['prevention']:
            lines.append("")
            lines.append(f"🛡️ **预防建议**")
            lines.append(exp['prevention'])
        
        # 9. 免责声明
        lines.append("")
        lines.append("---")
        lines.append("⚠️ **提示**：以上信息仅供参考，不能替代专业医生的诊断和治疗建议。如有不适，请及时就医。")
        
        return "\n".join(lines)
    
    def _format_description(self, desc: str) -> str:
        """格式化疾病描述"""
        if not desc:
            return ""
        # 截取前200字
        if len(desc) > 200:
            desc = desc[:200] + "..."
        return desc.replace("\n", " ")
    
    def _format_cause(self, cause: str) -> str:
        """格式化病因"""
        if not cause:
            return ""
        # 截取前150字
        if len(cause) > 150:
            cause = cause[:150] + "..."
        return cause.replace("\n", " ")
    
    def _format_prevention(self, prevent: str) -> str:
        """格式化预防建议"""
        if not prevent:
            return ""
        # 截取前200字
        if len(prevent) > 200:
            prevent = prevent[:200] + "..."
        return prevent.replace("\n", " ")
    
    def _generate_notes(self, disease) -> List[str]:
        """生成注意事项"""
        notes = []
        
        if disease.get_prob:
            notes.append(f"发病率：{disease.get_prob}")
        if disease.easy_get:
            notes.append(f"易感人群：{disease.easy_get}")
        if disease.get_way and disease.get_way != "无传染性":
            notes.append(f"传播途径：{disease.get_way}")
        if disease.acompany:
            notes.append(f"可能并发症：{', '.join(disease.acompany[:3])}")
        
        return notes
    
    def _generate_fallback_response(self, symptoms: List[str]) -> Dict[str, Any]:
        """生成备用响应（未找到匹配疾病时）"""
        return {
            "disease_name": "未知",
            "match_score": 0,
            "description": "根据您的症状，暂时无法确定具体疾病。",
            "departments": ["内科", "全科门诊"],
            "notes": ["建议前往医院进行详细检查"]
        }
    
    def _generate_simple_response(
        self, 
        symptoms: List[str], 
        departments: Optional[List[str]]
    ) -> str:
        """生成简单响应（无RAG数据时）"""
        lines = []
        lines.append(f"根据您描述的{'、'.join(symptoms)}等症状，")
        
        if departments:
            lines.append(f"推荐就诊科室：{', '.join(departments)}")
        else:
            lines.append("建议前往内科或全科门诊就诊。")
        
        lines.append("")
        lines.append("⚠️ 请尽快就医，由专业医生进行诊断。")
        
        return "\n".join(lines)


# 便捷函数
def create_rag_system() -> Tuple[DiseaseRAGRetriever, DiseaseExplanationGenerator]:
    """
    快速创建RAG系统
    
    优先使用 MySQL 后端（低内存），不可用时回退到 JSON 文件
    """
    try:
        from database import DiseaseModel, get_db_session, get_engine
        from sqlalchemy import inspect, func
        engine = get_engine()
        if inspect(engine).has_table('diseases'):
            with get_db_session() as db:
                count = db.query(func.count(DiseaseModel.id)).scalar()
            if count and count > 0:
                print(f"[RAG] 使用 MySQL 后端，共 {count} 条疾病")
                retriever = DBDiseaseRetriever()
                generator = DBExplanationGenerator(retriever)
                return retriever, generator
    except Exception as e:
        print(f"[RAG] MySQL 后端不可用 ({e})，回退 JSON 文件")

    # 回退到 in-memory JSON
    print("[RAG] 使用 JSON 文件后端 (注意：内存占用高)")
    retriever = DiseaseRAGRetriever()
    generator = DiseaseExplanationGenerator(retriever)
    return retriever, generator


class DBDiseaseRetriever:
    """MySQL 后端疾病检索器 — 零内存加载，每次请求查询数据库"""

    def retrieve(
        self,
        symptoms: List[str],
        body_part: Optional[str] = None,
        top_k: int = 5,
    ) -> List[RetrievedDisease]:
        from database import search_diseases
        diseases = search_diseases(symptoms, top_k=top_k)

        results: List[RetrievedDisease] = []
        for d in diseases:
            matched = [s for s in symptoms if s in json.dumps(d.get('symptom', []), ensure_ascii=False)]
            disease = type('Disease', (), {
                'name': d.get('name', ''),
                'desc': d.get('desc', ''),
                'symptom': d.get('symptom', []),
                'cause': d.get('cause', ''),
                'cure_department': d.get('cure_department', []),
                'cure_way': d.get('cure_way', []),
                'cure_lasttime': d.get('cure_lasttime', ''),
                'cured_prob': d.get('cured_prob', ''),
                'common_drug': d.get('common_drug', []),
                'do_eat': d.get('do_eat', []),
                'not_eat': d.get('not_eat', []),
                'prevent': d.get('prevent', ''),
                'check': d.get('check', []),
                'get_prob': d.get('get_prob', ''),
                'easy_get': d.get('easy_get', ''),
                'get_way': d.get('get_way', ''),
                'acompany': d.get('acompany', []),
                'cost_money': d.get('cost_money', ''),
            })()
            results.append(RetrievedDisease(
                name=d.get('name', ''),
                score=min(len(matched) / max(len(symptoms), 1), 1.0),
                disease=disease,
                matched_symptoms=matched,
            ))
        return results

    def get_disease_detail(self, disease_name: str) -> Optional[Any]:
        from database import DiseaseModel, get_db_session
        with get_db_session() as db:
            row = db.query(DiseaseModel).filter_by(name=disease_name).first()
            if not row:
                return None
            d = row.to_legacy_dict()
            disease = type('Disease', (), {
                'name': d.get('name', ''),
                'desc': d.get('desc', ''),
                'symptom': d.get('symptom', []),
                'cause': d.get('cause', ''),
                'cure_department': d.get('cure_department', []),
                'cure_way': d.get('cure_way', []),
                'cure_lasttime': d.get('cure_lasttime', ''),
                'cured_prob': d.get('cured_prob', ''),
                'common_drug': d.get('common_drug', []),
                'do_eat': d.get('do_eat', []),
                'not_eat': d.get('not_eat', []),
                'prevent': d.get('prevent', ''),
                'check': d.get('check', []),
                'get_prob': d.get('get_prob', ''),
                'easy_get': d.get('easy_get', ''),
                'get_way': d.get('get_way', ''),
                'acompany': d.get('acompany', []),
                'cost_money': d.get('cost_money', ''),
            })()
            return disease


class DBExplanationGenerator(DiseaseExplanationGenerator):
    """MySQL 后端的疾病解释生成器 — 继承原逻辑，仅更换检索器"""
    pass


if __name__ == "__main__":
    # 测试
    print("初始化RAG系统...")
    retriever, generator = create_rag_system()
    
    # 测试检索
    print("\n测试检索：头痛、发热")
    results = retriever.retrieve(["头痛", "发热"])
    for r in results[:3]:
        print(f"  {r.name}: {r.score:.2f} (匹配症状: {r.matched_symptoms})")
    
    # 测试生成解释
    print("\n测试生成增强回复：")
    response = generator.generate_enhanced_response(
        ["头痛", "发热", "鼻塞"],
        body_part="头颅",
        department_recommendation=["内科普通门诊"]
    )
    print(response)
