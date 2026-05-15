"""
医学知识库数据加载工具
用于加载和处理 medical.json 数据文件
"""
import json
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Disease:
    """疾病数据模型"""
    name: str                          # 疾病名称
    desc: str = ""                     # 疾病描述
    category: List[str] = None         # 疾病分类
    symptom: List[str] = None          # 症状列表
    cause: str = ""                    # 病因
    prevent: str = ""                  # 预防措施
    cure_department: List[str] = None  # 就诊科室
    cure_way: List[str] = None         # 治疗方式
    cure_lasttime: str = ""            # 治疗周期
    cured_prob: str = ""               # 治愈概率
    check: List[str] = None            # 检查项目
    common_drug: List[str] = None      # 常用药物
    recommand_drug: List[str] = None   # 推荐药物
    drug_detail: List[str] = None      # 药品详情
    do_eat: List[str] = None           # 宜吃食物
    not_eat: List[str] = None          # 忌吃食物
    recommand_eat: List[str] = None    # 推荐食谱
    get_prob: str = ""                 # 发病率
    get_way: str = ""                  # 传播途径
    easy_get: str = ""                 # 易感人群
    yibao_status: str = ""             # 医保状态
    acompany: List[str] = None         # 并发症
    cost_money: str = ""               # 治疗费用
    
    def __post_init__(self):
        """初始化列表字段"""
        if self.category is None:
            self.category = []
        if self.symptom is None:
            self.symptom = []
        if self.cure_department is None:
            self.cure_department = []
        if self.cure_way is None:
            self.cure_way = []
        if self.check is None:
            self.check = []
        if self.common_drug is None:
            self.common_drug = []
        if self.recommand_drug is None:
            self.recommand_drug = []
        if self.drug_detail is None:
            self.drug_detail = []
        if self.do_eat is None:
            self.do_eat = []
        if self.not_eat is None:
            self.not_eat = []
        if self.recommand_eat is None:
            self.recommand_eat = []
        if self.acompany is None:
            self.acompany = []
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Disease':
        """从字典创建 Disease 对象"""
        return cls(
            name=data.get('name', ''),
            desc=data.get('desc', ''),
            category=data.get('category', []),
            symptom=data.get('symptom', []),
            cause=data.get('cause', ''),
            prevent=data.get('prevent', ''),
            cure_department=data.get('cure_department', []),
            cure_way=data.get('cure_way', []),
            cure_lasttime=data.get('cure_lasttime', ''),
            cured_prob=data.get('cured_prob', ''),
            check=data.get('check', []),
            common_drug=data.get('common_drug', []),
            recommand_drug=data.get('recommand_drug', []),
            drug_detail=data.get('drug_detail', []),
            do_eat=data.get('do_eat', []),
            not_eat=data.get('not_eat', []),
            recommand_eat=data.get('recommand_eat', []),
            get_prob=data.get('get_prob', ''),
            get_way=data.get('get_way', ''),
            easy_get=data.get('easy_get', ''),
            yibao_status=data.get('yibao_status', ''),
            acompany=data.get('acompany', []),
            cost_money=data.get('cost_money', '')
        )
    
    def to_rag_text(self) -> str:
        """
        转换为适合RAG的文本格式
        将疾病信息整合为一段连续的文本
        """
        sections = []
        
        # 标题
        sections.append(f"【疾病名称】{self.name}")
        
        # 分类
        if self.category:
            sections.append(f"【疾病分类】{' > '.join(self.category)}")
        
        # 描述
        if self.desc:
            desc = self.desc[:500] + "..." if len(self.desc) > 500 else self.desc
            sections.append(f"【疾病简介】{desc}")
        
        # 症状
        if self.symptom:
            sections.append(f"【常见症状】{', '.join(self.symptom)}")
        
        # 病因
        if self.cause:
            cause = self.cause[:300] + "..." if len(self.cause) > 300 else self.cause
            sections.append(f"【病因】{cause}")
        
        # 就诊科室
        if self.cure_department:
            sections.append(f"【就诊科室】{', '.join(self.cure_department)}")
        
        # 治疗方式
        if self.cure_way:
            sections.append(f"【治疗方式】{', '.join(self.cure_way)}")
        
        # 检查项目
        if self.check:
            sections.append(f"【相关检查】{', '.join(self.check)}")
        
        # 并发症
        if self.acompany:
            sections.append(f"【常见并发症】{', '.join(self.acompany)}")
        
        return "\n".join(sections)


class MedicalKnowledgeBase:
    """医学知识库管理类"""
    
    def __init__(self, data_file: str = None):
        """
        初始化知识库
        
        Args:
            data_file: 数据文件路径，默认为 knowledge_base/medical.json
        """
        if data_file is None:
            # 获取当前文件所在目录
            current_dir = Path(__file__).parent
            data_file = current_dir / "medical.json"
        
        self.data_file = Path(data_file)
        self.diseases: List[Disease] = []
        self._name_index: Dict[str, Disease] = {}
        self._symptom_index: Dict[str, List[Disease]] = {}
        self._department_index: Dict[str, List[Disease]] = {}
    
    def load(self) -> 'MedicalKnowledgeBase':
        """
        加载数据文件
        
        Returns:
            self，支持链式调用
        """
        print(f"正在加载医学知识库: {self.data_file}")
        
        if not self.data_file.exists():
            raise FileNotFoundError(f"数据文件不存在: {self.data_file}")
        
        count = 0
        with open(self.data_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    disease = Disease.from_dict(data)
                    self.diseases.append(disease)
                    self._update_indexes(disease)
                    count += 1
                    
                    if count % 1000 == 0:
                        print(f"  已加载 {count} 条记录...")
                        
                except json.JSONDecodeError as e:
                    print(f"  解析错误，跳过该行: {e}")
                    continue
        
        print(f"知识库加载完成，共 {count} 条疾病记录")
        return self
    
    def _update_indexes(self, disease: Disease):
        """更新索引"""
        # 名称索引
        self._name_index[disease.name] = disease
        
        # 症状索引
        for symptom in disease.symptom:
            if symptom not in self._symptom_index:
                self._symptom_index[symptom] = []
            self._symptom_index[symptom].append(disease)
        
        # 科室索引
        for dept in disease.cure_department:
            if dept not in self._department_index:
                self._department_index[dept] = []
            self._department_index[dept].append(disease)
    
    def get_by_name(self, name: str) -> Optional[Disease]:
        """根据疾病名称获取"""
        return self._name_index.get(name)
    
    def search_by_symptom(self, symptom: str) -> List[Disease]:
        """根据症状搜索疾病"""
        return self._symptom_index.get(symptom, [])
    
    def search_by_department(self, department: str) -> List[Disease]:
        """根据科室搜索疾病"""
        return self._department_index.get(department, [])
    
    def fuzzy_search(self, keyword: str) -> List[Disease]:
        """
        模糊搜索（在名称、症状、描述中搜索）
        
        Args:
            keyword: 搜索关键词
            
        Returns:
            匹配的疾病列表
        """
        results = []
        keyword_lower = keyword.lower()
        
        for disease in self.diseases:
            # 搜索名称
            if keyword_lower in disease.name.lower():
                results.append(disease)
                continue
            
            # 搜索症状
            for symptom in disease.symptom:
                if keyword_lower in symptom.lower():
                    results.append(disease)
                    break
            else:
                # 搜索描述
                if disease.desc and keyword_lower in disease.desc.lower():
                    results.append(disease)
        
        return results
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取知识库统计信息"""
        return {
            "total_diseases": len(self.diseases),
            "total_symptoms": len(self._symptom_index),
            "total_departments": len(self._department_index),
            "departments": list(self._department_index.keys())[:20],  # 前20个科室
            "top_symptoms": sorted(
                self._symptom_index.items(),
                key=lambda x: len(x[1]),
                reverse=True
            )[:10]  # 最常见的10个症状
        }
    
    def export_for_rag(self, output_file: str):
        """
        导出为RAG可用的文本格式
        
        Args:
            output_file: 输出文件路径
        """
        print(f"正在导出RAG格式数据到: {output_file}")
        
        with open(output_file, 'w', encoding='utf-8') as f:
            for i, disease in enumerate(self.diseases):
                rag_text = disease.to_rag_text()
                f.write(f"=== 疾病记录 {i+1} ===\n")
                f.write(rag_text)
                f.write("\n\n")
                
                if (i + 1) % 1000 == 0:
                    print(f"  已导出 {i+1} 条记录...")
        
        print(f"导出完成，共 {len(self.diseases)} 条记录")


# 便捷函数
def load_knowledge_base(data_file: str = None) -> MedicalKnowledgeBase:
    """
    快速加载知识库
    
    Args:
        data_file: 数据文件路径
        
    Returns:
        加载好的 MedicalKnowledgeBase 实例
    """
    kb = MedicalKnowledgeBase(data_file)
    return kb.load()


if __name__ == "__main__":
    # 测试加载
    kb = load_knowledge_base()
    
    # 打印统计信息
    stats = kb.get_statistics()
    print("\n=== 知识库统计 ===")
    print(f"疾病总数: {stats['total_diseases']}")
    print(f"症状总数: {stats['total_symptoms']}")
    print(f"科室总数: {stats['total_departments']}")
    
    # 测试搜索
    print("\n=== 测试搜索 ===")
    results = kb.fuzzy_search("头痛")
    print(f"搜索'头痛'，找到 {len(results)} 条结果")
    if results:
        print(f"第一条: {results[0].name}")
        print(f"症状: {results[0].symptom[:5]}")
    
    # 测试RAG文本生成
    print("\n=== RAG文本示例 ===")
    if results:
        print(results[0].to_rag_text()[:500])
