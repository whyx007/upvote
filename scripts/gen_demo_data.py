"""随机生成演示数据 Excel（符合导入模板四表格式）。

规模：初中三个年级 × 10 班 × 40 人 = 1200 学生；
师资：按年级实际科目配齐，每科 3 位教师分担 10 个班（3/3/4）；
学号：入学年份(4) + 班级(2) + 班内序号(2)，顺序编码；
小组：每班 6 个学习小组（7/7/7/7/6/6 人）。

用法：python scripts/gen_demo_data.py [输出路径]
默认输出 data/demo_import.xlsx
"""
import os
import random
import sys

from openpyxl import Workbook

random.seed(20261113)

SURNAMES = (
    "王李张刘陈杨黄赵吴周徐孙马朱胡郭何林罗高郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔钟谭陆汪范金石廖贾夏韦方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤"
)
GIVEN = (
    "伟芳娜敏静丽强磊军洋勇艳杰娟涛明超秀兰霞平刚桂英华玉萍红娥玲芬燕彬鹏浩宇轩然博宁毅俊峰志斌成康新利清吉安邦承乐发厚庆民友裕河哲江亮政谦亨奇固之轮翰朗伯宏言若鸣朋梁栋维启克伦翔旭泽晨辰士以建家致树炎德行时泰盛雄琛钧冠策腾楠榕风航弘倩莹雪琳晗瑶允元源远和璧婕馨瑗琰融园艺咏卿聪澜纯毓悦昭冰爽琬茗羽希欣飘育滢馥筠柔竹霭凝晓欢霄枫芸菲寒伊亚宜可姬舒影思佳嘉琼勤珍贞莉娣璐娅琦晶妍茜秋珊莎锦黛青婷姣婉娴瑾颖露怡婵雁蓓纨仪荷丹蓉眉君琴蕊薇菁梦岚苑韵"
)

GRADES = [
    ("初一", 2026, ["语文", "数学", "英语", "道德与法治", "历史", "地理", "生物", "体育", "音乐", "美术", "信息技术"]),
    ("初二", 2025, ["语文", "数学", "英语", "物理", "道德与法治", "历史", "地理", "生物", "体育", "音乐", "美术", "信息技术"]),
    ("初三", 2024, ["语文", "数学", "英语", "物理", "化学", "道德与法治", "历史", "体育", "音乐", "美术", "信息技术"]),
]
CLASSES_PER_GRADE = 10
STUDENTS_PER_CLASS = 40
GROUP_NAMES = ["星辰组", "追光组", "启航组", "破浪组", "凌云组", "笃行组"]
GROUP_SIZES = [7, 7, 7, 7, 6, 6]

used_names = set()


def random_name():
    while True:
        name = random.choice(SURNAMES) + "".join(random.sample(GIVEN, random.choice([1, 2])))
        if name not in used_names:
            used_names.add(name)
            return name


def random_phone():
    return "13" + "".join(str(random.randint(0, 9)) for _ in range(9))


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join("data", "demo_import.xlsx")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)

    students, teachers, groups, teaching = [], [], [], []
    teacher_no = 0

    for grade, year, subjects in GRADES:
        class_names = [f"{grade}{i}班" for i in range(1, CLASSES_PER_GRADE + 1)]
        # 学生：顺序学号 = 入学年份 + 班级序号 + 班内序号
        for ci, class_name in enumerate(class_names, start=1):
            class_student_nos = []
            for si in range(1, STUDENTS_PER_CLASS + 1):
                student_no = f"{year}{ci:02d}{si:02d}"
                students.append([student_no, random_name(), grade, class_name, year, random.choice(["男", "女"])])
                class_student_nos.append(student_no)
            # 学习小组
            offset = 0
            for gname, size in zip(GROUP_NAMES, GROUP_SIZES):
                members = class_student_nos[offset:offset + size]
                offset += size
                groups.append([gname, class_name, ",".join(members)])
        # 教师：每科 3 人分担 10 个班（3/3/4）
        for subject in subjects:
            for chunk in (class_names[0:3], class_names[3:6], class_names[6:10]):
                teacher_no += 1
                emp = f"T{teacher_no:03d}"
                teachers.append([emp, random_name(), random_phone(), "123456", "teacher", subject])
                for class_name in chunk:
                    teaching.append([emp, class_name])

    wb = Workbook()
    wb.remove(wb.active)
    for name, header, rows in [
        ("学生", ["学号", "姓名", "年级", "班级", "入学年份", "性别"], students),
        ("教师", ["工号", "姓名", "手机号", "初始密码", "角色", "学科"], teachers),
        ("小组", ["小组名称", "班级", "成员学号"], groups),
        ("任教", ["工号", "班级"], teaching),
    ]:
        ws = wb.create_sheet(name)
        ws.append(header)
        for row in rows:
            ws.append(row)
    wb.save(out)
    print(f"生成完成：{out}")
    print(f"学生 {len(students)} 人 | 教师 {len(teachers)} 人 | 小组 {len(groups)} 个 | 任教关系 {len(teaching)} 条")


if __name__ == "__main__":
    main()