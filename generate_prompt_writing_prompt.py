import os
from pathlib import Path

def generate_prompt():
    ref_nb = "hmumu.py"
    output_file = "prompt_writing_prompt.md"
    agents_file = "AGENTS.md"
    skills_dir = "skills"

    with open(output_file, 'w', encoding='utf-8') as out_f:
        # ==========================================
        # 0. 处理Jupyter Notebook
        # ==========================================
        out_f.write("## Jupyter Notebook\n```\n")
        with open("skills/sm-ana-aod/ana-fitting/references/" + ref_nb, 'r', encoding='utf-8') as nb_f:
            for line in nb_f:
                out_f.write(line)

        out_f.write("\n```\n\n")
        # ==========================================
        # 1. 处理 AGENTS.md
        # ==========================================
        out_f.write("## Analysis Workflow References\n")
        out_f.write("```\n")
        if os.path.exists(agents_file):
            with open(agents_file, 'r', encoding='utf-8') as f:
                recording = False
                for line in f:
                    # 写入截取的内容
                    if recording:
                        out_f.write(line)

                    # 匹配起始行
                    if line.strip().startswith("## Analysis Workflow References"):
                        recording = True
                    
                    # 匹配结束行（不包含这一行）
                    if line.strip().startswith("## Make It Yours"):
                        break
        else:
            print(f"⚠️ 警告: 未找到 {agents_file} 文件")

        # 增加一个换行，确保两部分内容不会粘在一起
        out_f.write("```\n\n")

        # ==========================================
        # 2. 处理 skills/**/*.json
        # ==========================================
        # 使用 rglob 递归查找所有 json 文件
        skill_files = sorted(Path(skills_dir).rglob("*.json"))
        
        if not skill_files:
            print(f"⚠️ 警告: 在 {skills_dir}/ 目录下未找到任何 JSON 文件")
            
        for filepath in skill_files:
            # 获取纯文件名（不含父路径）
            filename = filepath.name 
            
            out_f.write(f"### {filename}\n")
            out_f.write("```json\n")
            
            with open(filepath, 'r', encoding='utf-8') as json_f:
                content = json_f.read()
                out_f.write(content)
                # 确保 json 内容最后有一个换行，防止反引号粘连
                if not content.endswith('\n'):
                    out_f.write('\n')
                    
            out_f.write("```\n\n")

        out_f.write("请根据这个Jupyter Notebook中的内容，和已经提供的例子: 1. 生成这个workflow xml块。 2. 生成selections.json 3. 生成fitting.json (注：假如Jupyter Notebook没有包含fitting代码，请自行分析，在json增加物理的fitting field)\n")

    print(f"✅ 成功生成文件: {output_file}")

if __name__ == "__main__":
    generate_prompt()
