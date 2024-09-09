import datetime
import re
import json
from bs4 import BeautifulSoup
import requests
from getpass import getpass
from urllib.parse import quote

session = requests.Session()

login_url = "https://sso.buaa.edu.cn/login?service="
jwxt_url = "https://byxt.buaa.edu.cn"
api_url = "https://byxt.buaa.edu.cn/jwapp/sys/homeapp/api/home/student/getMyScheduleDetail.do?"

def get_token(session: requests.Session, target: str) -> str:
    response = session.get(target)
    soup = BeautifulSoup(response.text, 'html.parser')
    token = soup.find('input', {'name': 'execution'})['value']
    return token


def login(session: requests.Session, target_url: str, username: str, password: str) -> bool:
    target = login_url + quote(target_url, 'utf-8')
    form = {
        'username': username,
        'password': password,
        'execution': get_token(session, target),
        '_eventId': 'submit',
        'type': 'username_password',
        'submit': "LOGIN"
    }
    response = session.post(target, data=form, allow_redirects=True)
    soup = BeautifulSoup(response.text, 'html.parser')

    if soup.script.string is not None:
        target_url = jwxt_url + soup.script.string.split('\'')[1]
        response = session.get(target_url)
        return True
    return False
    
    
def extract_week_and_teacher_info(text):
    week_ranges = re.findall(r'(\d+-\d+周|\d+周)', text)
    
    weeks = set()
    for week_range in week_ranges:
        if '-' in week_range:
            start, end = map(int, week_range[:-1].split('-'))
            weeks.update(range(start, end + 1))
        else:
            weeks.add(int(week_range[:-1]))
    
    return sorted(weeks)
    
def generate_ics(title: str, class_list: list) -> str:
    ics_payload = f"""BEGIN:VCALENDAR
VERSION:2.0
X-WR-CALNAME:{title}
CALSCALE:GREGORIAN
BEGIN:VTIMEZONE
TZID:Asia/Shanghai
TZURL:http://tzurl.org/zoneinfo-outlook/Asia/Shanghai
X-LIC-LOCATION:Asia/Shanghai
BEGIN:STANDARD
TZOFFSETFROM:+0800
TZOFFSETTO:+0800
TZNAME:CST
DTSTART:19700101T000000
END:STANDARD
END:VTIMEZONE"""

    for class_info in class_list:
        event_start = f'{class_info["date"]}T{class_info["start"].rjust(4, "0")}00'
        event_end = f'{class_info["date"]}T{class_info["end"].rjust(4, "0")}00'
        event_description = f"""编号：{class_info["course_id"]}
名称：{class_info["course_name"]}
教师：{class_info["teacher"]}
学分：{class_info["credit"]}
上课时间：{class_info["course_time"]}；第 {class_info["lessons"]} 节""".replace("\n", "\\n")
        event_info = f"""
BEGIN:VEVENT
DESCRIPTION:{event_description}
DTSTART;TZID=Asia/Shanghai:{event_start}
DTEND;TZID=Asia/Shanghai:{event_end}
LOCATION:{class_info["location"]}
SUMMARY:{class_info["course_name"]}
BEGIN:VALARM
TRIGGER:-P0DT0H30M0S
REPEAT:1
DURATION:PT1M
END:VALARM
END:VEVENT"""
        ics_payload += event_info

    ics_payload += "\nEND:VCALENDAR"
    return ics_payload

if __name__ == "__main__":
    username = input('Enter username: ')
    password = getpass('Enter password: ')
    if not login(session, 'https://byxt.buaa.edu.cn/jwapp/sys/homeapp/index.do', username, password):
        print('Login failed')
        exit(1)
    print('Login success')
    print('Please enter term id (e.g. 2023-2024-1)')
    print('Autumn: 1, Spring: 2, Summer: 3')
    term_id = input('Enter term id: ')
    response = session.get(api_url + f'termCode={term_id}&type=term')
    if response.status_code != 200:
        print('Failed to get schedule')
        exit(1)
    data = json.loads(response.text)
    if not data.get('datas'):
        print('Failed to get schedule')
        exit(1)
        
    print('Please enter the date of the first Monday of the semester (e.g. 2024-09-02)')
    week_one_monday = input('Enter date: ')
    classes = data['datas']['arrangedList']

    class_list = []
    for klass in classes:
        class_info = {}
        weeks = extract_week_and_teacher_info(klass['titleDetail'][-2])
        class_info['course_id'] = klass['courseCode']
        class_info['course_name'] = klass['courseName']
        class_info['teacher'] = klass['titleDetail'][-2].split('/')[0]
        class_info['credit'] = klass['credit']
        class_info['course_time'] = klass['beginTime'] + '~' + klass['endTime']
        class_info['lessons'] = klass['cellDetail'][3]['text'][:-1]
        class_info['location'] = klass['placeName']
        class_info['start'] = klass['beginTime'][:2] + klass['beginTime'][3:5] + '00'
        class_info['end'] = klass['endTime'][:2] + klass['endTime'][3:5] + '00'
        dayOfWeek = klass['dayOfWeek']
        for week in weeks:
            day = datetime.datetime.strptime(week_one_monday, "%Y-%m-%d") + datetime.timedelta(days=dayOfWeek - 1) + datetime.timedelta(weeks=week-1)
            class_info['date'] = day.strftime("%Y%m%d")
            class_list.append(class_info.copy())
    ics_payload = generate_ics('calendar', class_list)
    with open('calendar.ics', 'w', encoding='utf-8') as f:
        f.write(ics_payload)
        
    print('Calendar saved as calendar.ics')