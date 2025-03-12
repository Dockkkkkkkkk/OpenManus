# OpenManus 任务管理系统

Manus is incredible, but OpenManus can achieve any ideas without an Invite Code 🛫!

OpenManus是一个智能任务管理系统，可以帮助用户创建、跟踪、管理各种任务和生成的文件。

## 特性

- 基于提示词创建和执行任务
- 使用MySQL数据库存储任务记录和文件信息
- 将日志和生成的文件存储在腾讯云对象存储(COS)上
- 支持文件下载和管理
- 实时任务状态更新

## Project Demo

<video src="https://private-user-images.githubusercontent.com/61239030/420168772-6dcfd0d2-9142-45d9-b74e-d10aa75073c6.mp4?jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3NDEzMTgwNTksIm5iZiI6MTc0MTMxNzc1OSwicGF0aCI6Ii82MTIzOTAzMC80MjAxNjg3NzItNmRjZmQwZDItOTE0Mi00NWQ5LWI3NGUtZDEwYWE3NTA3M2M2Lm1wND9YLUFtei1BbGdvcml0aG09QVdTNC1ITUFDLVNIQTI1NiZYLUFtei1DcmVkZW50aWFsPUFLSUFWQ09EWUxTQTUzUFFLNFpBJTJGMjAyNTAzMDclMkZ1cy1lYXN0LTElMkZzMyUyRmF3czRfcmVxdWVzdCZYLUFtei1EYXRlPTIwMjUwMzA3VDAzMjIzOVomWC1BbXotRXhwaXJlcz0zMDAmWC1BbXotU2lnbmF0dXJlPTdiZjFkNjlmYWNjMmEzOTliM2Y3M2VlYjgyNDRlZDJmOWE3NWZhZjE1MzhiZWY4YmQ3NjdkNTYwYTU5ZDA2MzYmWC1BbXotU2lnbmVkSGVhZGVycz1ob3N0In0.UuHQCgWYkh0OQq9qsUWqGsUbhG3i9jcZDAMeHjLt5T4" data-canonical-src="https://private-user-images.githubusercontent.com/61239030/420168772-6dcfd0d2-9142-45d9-b74e-d10aa75073c6.mp4?jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3NDEzMTgwNTksIm5iZiI6MTc0MTMxNzc1OSwicGF0aCI6Ii82MTIzOTAzMC80MjAxNjg3NzItNmRjZmQwZDItOTE0Mi00NWQ5LWI3NGUtZDEwYWE3NTA3M2M2Lm1wND9YLUFtei1BbGdvcml0aG09QVdTNC1ITUFDLVNIQTI1NiZYLUFtei1DcmVkZW50aWFsPUFLSUFWQ09EWUxTQTUzUFFLNFpBJTJGMjAyNTAzMDclMkZ1cy1lYXN0LTElMkZzMyUyRmF3czRfcmVxdWVzdCZYLUFtei1EYXRlPTIwMjUwMzA3VDAzMjIzOVomWC1BbXotRXhwaXJlcz0zMDAmWC1BbXotU2lnbmF0dXJlPTdiZjFkNjlmYWNjMmEzOTliM2Y3M2VlYjgyNDRlZDJmOWE3NWZhZjE1MzhiZWY4YmQ3NjdkNTYwYTU5ZDA2MzYmWC1BbXotU2lnbmVkSGVhZGVycz1ob3N0In0.UuHQCgWYkh0OQq9qsUWqGsUbhG3i9jcZDAMeHjLt5T4" controls="controls" muted="muted" class="d-block rounded-bottom-2 border-top width-fit" style="max-height:640px; min-height: 200px"></video>

## 安装

1. 创建新的conda环境:

```bash
conda create -n open_manus python=3.12
conda activate open_manus
```

2. 克隆仓库:

```bash
git clone https://github.com/mannaandpoem/OpenManus.git
cd OpenManus
```

3. 安装依赖:

```bash
pip install -r requirements.txt
```

4. 配置MySQL数据库：

OpenManus使用MySQL数据库存储任务和文件信息。您需要设置以下环境变量或在配置文件中指定：

```bash
# MySQL数据库配置
export MYSQL_HOST=localhost
export MYSQL_PORT=3306
export MYSQL_USER=openmanus
export MYSQL_PASSWORD=your_password
export MYSQL_DATABASE=openmanus
```

5. 配置腾讯云对象存储：

为了存储日志文件和生成的文件，您需要配置腾讯云COS：

```bash
# 腾讯云COS配置
export COS_SECRET_ID=your_secret_id
export COS_SECRET_KEY=your_secret_key
export COS_REGION=ap-nanjing  # 根据您的实际地区调整
export COS_BUCKET=your-bucket-name
```

## 数据库结构

OpenManus使用两个主要的数据表：

1. **tasks表** - 存储任务信息：
   - id: 任务ID (主键)
   - user_id: 用户ID
   - prompt: 提示词
   - status: 任务状态 (pending/running/completed/failed)
   - log_url: 日志文件在COS上的URL
   - created_at: 创建时间
   - updated_at: 更新时间
   - completed_at: 完成时间

2. **files表** - 存储任务生成的文件信息：
   - id: 文件ID (主键)
   - task_id: 关联的任务ID (外键)
   - filename: 文件名
   - cos_url: 文件在COS上的URL
   - content_type: 文件MIME类型
   - file_size: 文件大小
   - created_at: 创建时间

## 日志存储

为了高效地存储和管理任务日志，我们不再将日志内容直接存储在数据库中，而是：

1. 创建日志文件并上传到腾讯云COS
2. 在任务记录中仅存储日志文件的URL
3. 查看任务详情时，系统会自动从COS下载并显示日志内容

这种方式有以下优势：
- 数据库负载更小，不需要存储大量文本
- 日志文件大小不受数据库字段长度限制
- 可以直接通过URL访问日志文件

## 启动应用

启动方式如下：

```bash
python main.py
```

然后访问 http://localhost:8000 使用应用。

## API文档

API文档可在 http://localhost:8000/docs 查看。

## 贡献者

Our team members [@mannaandpoem](https://github.com/mannaandpoem) [@XiangJinyu](https://github.com/XiangJinyu) [@MoshiQAQ](https://github.com/MoshiQAQ) [@didiforgithub](https://github.com/didiforgithub) from [@MetaGPT](https://github.com/geekan/MetaGPT) built it within 3 hours!

It's a simple implementation, so we welcome any suggestions, contributions, and feedback!

## 许可证

Copyright © 2023 OpenManus. 保留所有权利。

## Configuration

OpenManus requires configuration for the LLM APIs it uses. Follow these steps to set up your configuration:

1. Create a `config.toml` file in the `config` directory (you can copy from the example):

```bash
cp config/config.example.toml config/config.toml
```

2. Edit `config/config.toml` to add your API keys and customize settings:

```toml
# Global LLM configuration
[llm]
model = "gpt-4o"
base_url = "https://api.openai.com/v1"
api_key = "sk-..."  # Replace with your actual API key
max_tokens = 4096
temperature = 0.0

# Optional configuration for specific LLM models
[llm.vision]
model = "gpt-4o"
base_url = "https://api.openai.com/v1"
api_key = "sk-..."  # Replace with your actual API key
```

## Quick Start
One line for run OpenManus:

```bash
python main.py
```

Then input your idea via terminal!

For unstable version, you also can run:

```bash
python run_flow.py
```

## How to contribute
We welcome any friendly suggestions and helpful contributions! Just create issues or submit pull requests.

Or contact @mannaandpoem via 📧email: mannaandpoem@gmail.com

## Roadmap
- [ ] Better Planning
- [ ] Live Demos
- [ ] Replay
- [ ] RL Fine-tuned Models
- [ ] Comprehensive Benchmarks

<!-- ## Community Group
Join our networking group and share your experience with other developers! -->

<!-- <div align="center" style="display: flex; gap: 20px;">
    <img src="assets/community_group_9.jpg" alt="OpenManus 交流群7" width="300" />
    <img src="assets/community_group_10.jpg" alt="OpenManus 交流群8" width="300" />
</div> -->
## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=mannaandpoem/OpenManus&type=Date)](https://star-history.com/#mannaandpoem/OpenManus&Date)

## Acknowledgement

Thanks to [anthropic-computer-use](https://github.com/anthropics/anthropic-quickstarts/tree/main/computer-use-demo) and [broswer-use](https://github.com/browser-use/browser-use) for providing basic support for this project!

OpenManus is built by contributors from MetaGPT. Huge thanks to this agent community!
