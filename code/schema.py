# schema.py - schema of DiseaseKG in Neo4j: node labels and properties, relationship types, a Chinese explanation of
# every field (the paper's "Chinese schema"), and Chinese trigger words used by the relevant-schema extractor.

NODES = {
    'Disease': [
        ('name', 'string', '疾病名称'), ('description', 'string', '疾病简介'), ('cause', 'string', '病因'),
        ('prevent', 'string', '预防措施'), ('category', 'string', '所属类别（疾病百科分类路径）'),
        ('easy_get', 'string', '易感人群'), ('get_way', 'string', '传播方式'), ('yibao_status', 'string', '是否医保'),
        ('get_prob', 'string', '患病比例（原文）'), ('cured_prob', 'string', '治愈率（原文）'),
        ('cure_lasttime', 'string', '治疗周期（原文）'), ('cost_money', 'string', '治疗费用（原文）'),
        ('cure_way', 'string', '治疗方式'), ('cure_department', 'string', '就诊科室（原文）'),
        ('get_prob_pct', 'double', '患病比例数值（%）'), ('cured_prob_pct', 'double', '治愈率数值（%）'),
        ('cure_days', 'double', '治疗周期上限（天）'), ('cost_min', 'double', '最低治疗费用（元）'),
        ('cost_max', 'double', '最高治疗费用（元）')],
    'Symptom': [('name', 'string', '症状名称')],
    'Drug': [('name', 'string', '药品名称')],
    'Food': [('name', 'string', '食物名称')],
    'Check': [('name', 'string', '检查项目名称')],
    'Department': [('name', 'string', '科室名称')],
    'Producer': [('name', 'string', '药品生产厂商名称')],
}
NODE_CN = {'Disease': '疾病', 'Symptom': '症状', 'Drug': '药品', 'Food': '食物', 'Check': '检查项目',
           'Department': '科室', 'Producer': '生产厂商'}
RANK = ('rank', 'int', '在原始列表中的排序位次（1 为第一位）')
RNAME = ('name', 'string', '关系中文名')
EDGES = [
    ('has_symptom', 'Disease', 'Symptom', '疾病的症状', [RNAME, RANK]),
    ('need_check', 'Disease', 'Check', '疾病需要做的诊断检查', [RNAME, RANK]),
    ('common_drug', 'Disease', 'Drug', '疾病的常用药品', [RNAME, RANK]),
    ('recommand_drug', 'Disease', 'Drug', '疾病的好评（推荐）药品', [RNAME, RANK]),
    ('do_eat', 'Disease', 'Food', '疾病宜吃的食物', [RNAME, RANK]),
    ('no_eat', 'Disease', 'Food', '疾病忌吃的食物', [RNAME, RANK]),
    ('recommand_eat', 'Disease', 'Food', '疾病的推荐食谱', [RNAME, RANK]),
    ('acompany_with', 'Disease', 'Disease', '疾病的并发症', [RNAME, RANK]),
    ('belongs_to', 'Disease', 'Department', '疾病所属（就诊）科室', [RNAME]),
    ('belongs_to', 'Department', 'Department', '小科室所属的大科室', [RNAME]),
    ('drugs_of', 'Producer', 'Drug', '厂商生产的药品', [RNAME]),
]

# Chinese trigger words -> schema item. Used by the verifier (is every GQL item verbalised in the NL?)
# and by the relevant-schema extractor (keyword part of the label linker).
PROP_TRIGGERS = {
    'description': ['简介', '介绍', '描述', '是一种什么', '什么病', '概述', '说明', '是什么疾病'],
    'cause': ['病因', '原因', '引起', '导致', '成因', '诱因'],
    'prevent': ['预防', '防止', '避免'],
    'category': ['分类', '类别', '归类'],
    'easy_get': ['易感', '容易得', '易发', '好发', '高发人群', '人群', '容易患'],
    'get_way': ['传播', '传染', '途径'],
    'yibao_status': ['医保'],
    'get_prob': ['患病比例', '发病率', '患病率', '患病概率', '得病概率'],
    'cured_prob': ['治愈率', '治愈概率', '治好', '治愈的可能', '治愈几率'],
    'cure_lasttime': ['治疗周期', '治疗时间', '多长时间', '多久', '疗程'],
    'cost_money': ['费用', '花费', '多少钱', '花多少'],
    'cure_way': ['治疗方式', '治疗方法', '怎么治', '如何治', '疗法', '治疗手段'],
    'cure_department': ['就诊科室'],
    'get_prob_pct': ['患病比例', '发病率', '患病率', '患病概率', '得病概率'],
    'cured_prob_pct': ['治愈率', '治愈概率', '治愈几率', '治好'],
    'cure_days': ['治疗周期', '治疗时间', '天', '疗程', '多久', '治疗时长'],
    'cost_min': ['最低', '最少', '下限', '至少'],
    'cost_max': ['最高', '最多', '上限', '最贵'],
    'rank': ['首选', '前', '第', '排名', '排序', '位次', '首位', '排在', '列在'],
}
EDGE_TRIGGERS = {
    'has_symptom': ['症状', '表现', '症候', '出现'],
    'need_check': ['检查', '检测', '化验'],
    'common_drug': ['常用药', '常用的药', '常用药品', '用什么药', '吃什么药', '常用'],
    'recommand_drug': ['推荐药', '好评药', '推荐的药', '推荐药品', '好评'],
    'do_eat': ['宜吃', '适合吃', '可以吃', '宜食', '能吃', '适宜吃', '多吃'],
    'no_eat': ['忌吃', '不能吃', '不宜吃', '忌口', '禁食', '避免吃', '不要吃'],
    'recommand_eat': ['推荐食谱', '食谱', '推荐菜', '食疗'],
    'acompany_with': ['并发症', '并发', '伴随', '合并'],
    'belongs_to': ['科室', '科', '属于', '挂', '归属', '上级', '就诊'],
    'drugs_of': ['生产', '厂家', '厂商', '药企', '制药', '出品'],
}
LABEL_TRIGGERS = {
    'Disease': ['疾病', '病', '并发症', '患者'],
    'Symptom': ['症状', '表现'],
    'Drug': ['药', '药品'],
    'Food': ['食物', '吃', '食谱', '食'],
    'Check': ['检查', '检测', '化验'],
    'Department': ['科室', '科'],
    'Producer': ['厂家', '厂商', '药企', '生产', '制药'],
}



def render_schema(nodes=None, edges=None, cn=True, props=None):
    """Paper's flattened schema format (Table 1/2). nodes: iterable of labels; edges: iterable of
    (name, src, dst) triples. cn=True appends the Chinese explanation of every field (paper's
    'Chinese schema'); props: optional {label: set(prop)} to restrict node properties."""
    nodes = list(NODES) if nodes is None else [n for n in NODES if n in set(nodes)]
    if edges is None:
        eds = EDGES
    else:
        es = set(tuple(e) for e in edges)
        eds = [e for e in EDGES if (e[0], e[1], e[2]) in es]
    out = ['Nodes']
    for n in nodes:
        ps = NODES[n]
        if props and n in props:
            ps = [p for p in ps if p[0] in props[n] or p[0] == 'name']
        if cn:
            pl = ', '.join(f"('{p}', '{t}', '{c}')" for p, t, c in ps)
            out.append(f"{{'tag': '{n}', 'explain': '{NODE_CN[n]}', 'properties': [{pl}]}}")
        else:
            pl = ', '.join(f"('{p}', '{t}')" for p, t, c in ps)
            out.append(f"{{'tag': '{n}', 'properties': [{pl}]}}")
    out.append('Edges')
    for name, s, d, c, ps in eds:
        if cn:
            pl = ', '.join(f"('{p}', '{t}', '{x}')" for p, t, x in ps)
            out.append(f"{{'edge': '{name}', 'explain': '{c}', 'start_tag': '{s}', 'end_tag': '{d}', 'properties': [{pl}]}}")
        else:
            pl = ', '.join(f"('{p}', '{t}')" for p, t, x in ps)
            out.append(f"{{'edge': '{name}', 'start_tag': '{s}', 'end_tag': '{d}', 'properties': [{pl}]}}")
    return '\n'.join(out)
