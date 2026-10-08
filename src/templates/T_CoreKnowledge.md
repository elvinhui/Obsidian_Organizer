---
创建时间: {{ creation_date }}
知识分类: {{ category }}
状态: {{ status }}
标签: {{ tags }}
---
# {{ title }}

## 💡 核心概念与启发 (Core Insight)
> **一句话总结：** {{ core_concepts }}

## 🛠️ 落地与实践 (If-Then 战备触发器)
{{ action_sop }}

## 🔗 盲区与关联反思 (Connections)
{{ connections }}

{% if viewpoints_timestamps %}
## ⏱️ 核心观点时间戳 (Key Viewpoints & Timestamps)
{{ viewpoints_timestamps }}
{% endif %}
