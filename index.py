# -*- coding: utf-8 -*-
import uuid
import requests
import sys
import json
import yaml
import login
from datetime import datetime, timedelta, timezone
from pyDes import des, CBC, PAD_PKCS5
import base64

############配置############
Cookies = {
    'acw_tc': '2f624a1e16041604400635673e06de2b50cb475d9f787a0c87802ba71ce1fd',
    'MOD_AUTH_CAS': 'AE3XNxqT8sbBzaVttZ9zbW1601827579',
}
CpdailyInfo = 'Iy86UyNyPEZLgaS6S4YIDfNJIJcu1sU1SjcRPxRPCDT8jtWlr65OMgjhR0FoO7t9HmoDtE/UX3/fEbBDyYHWxbUxMqFNTFTun+/O9iw0p7zyE2I1tJlkxg5Ps72/gzgK3FF2M4nqT7LjpoSPO9gkV6LXqdZ3EvpfewBIKNIPW8UgCTcH4oB+cXdG2hmlNHX4cWu+1AWdAl/SRUSB1Nvo3pAeMdlt1PqQdQ1HQ1vgzpeb4WO2qLm34keqHUGz7R4fav5PcOsQwDfEtal+FxK29YhIWCEksAJf'
sessionToken = '329384c1-3263-4578-a3ca-e8338fcc8333'
############配置############

# 全局

host = login.host
session = requests.session()
session.cookies = requests.utils.cookiejar_from_dict(Cookies)


# 读取yml配置
def getYmlConfig(yaml_file='config.yml'):
    file = open(yaml_file, 'r', encoding="utf-8")
    file_data = file.read()
    file.close()
    config = yaml.load(file_data, Loader=yaml.FullLoader)
    return dict(config)


config = getYmlConfig()
user = config['user']


# 获取当前utc时间，并格式化为北京时间
def getTimeStr():
    utc_dt = datetime.utcnow().replace(tzinfo=timezone.utc)
    bj_dt = utc_dt.astimezone(timezone(timedelta(hours=8)))
    return bj_dt.strftime("%Y-%m-%d %H:%M:%S")


# 输出调试信息，并及时刷新缓冲区
def log(content):
    print(getTimeStr() + ' ' + str(content))
    sys.stdout.flush()


# 获取最新未签到任务
def getUnSignedTasks():
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.97 Safari/537.36',
        'content-type': 'application/json',
        'Accept-Encoding': 'gzip,deflate',
        'Accept-Language': 'zh-CN,en-US;q=0.8',
        'Content-Type': 'application/json;charset=UTF-8'
    }
    params = {}
    # url = 'https://{host}/wec-counselor-sign-apps/stu/sign/getStuSignInfosInOneDay'.format(host=host)
    url = 'https://{host}/wec-counselor-sign-apps/stu/sign/queryDailySginTasks'.format(host=host)
    res = session.post(url=url, headers=headers, data=json.dumps(params))
    # log(res.json())
    unSignedTasks = res.json()['datas']['unSignedTasks']
    if len(unSignedTasks) < 1:
        log('当前没有未签到任务')
        exit(-1)
    # 若任务有两个以上
    elif (len(unSignedTasks) > 1):
        for unSignedTask in unSignedTasks:
            taskName = unSignedTask['taskName']
            if (taskName == "全校学生每日健康信息报送"):
                latestTask = unSignedTask
    else:  # 只有一个任务的情况
        # 傻狗学校有两个未签到任务，一个是每日的一个是两个月结算的。两个月结算的被顶到最上面了
        # latestTask = unSignedTasks[0]
        taskName = unSignedTasks[0]['taskName']
        if (taskName != "全校学生每日健康信息报送"):
            print("签到任务已经完成")
            exit(-1)
        latestTask = unSignedTasks[0]
    return {
        'signInstanceWid': latestTask['signInstanceWid'],
        'signWid': latestTask['signWid']
    }


# 获取签到任务详情
def getDetailTask(params):
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.97 Safari/537.36',
        'content-type': 'application/json',
        'Accept-Encoding': 'gzip,deflate',
        'Accept-Language': 'zh-CN,en-US;q=0.8',
        'Content-Type': 'application/json;charset=UTF-8'
    }
    res = session.post(
        url='https://{host}/wec-counselor-sign-apps/stu/sign/detailSignTaskInst'.format(host=host),
        headers=headers, data=json.dumps(params))
    data = res.json()['datas']
    return data


# 填充表单
def fillForm(task):
    form = {}
    form['signPhotoUrl'] = ''
    if task['isNeedExtra'] == 1:
        extraFields = task['extraField']
        defaults = config['cpdaily']['defaults']
        extraFieldItemValues = []
        for i in range(0, len(extraFields)):
            default = defaults[i]['default']
            extraField = extraFields[i]
            if default['title'] != extraField['title']:
                log('第%d个默认配置项错误，请检查' % (i + 1))
                exit(-1)
            extraFieldItems = extraField['extraFieldItems']
            for extraFieldItem in extraFieldItems:
                if extraFieldItem['content'] == default['value']:
                    extraFieldItemValue = {'extraFieldItemValue': default['value'],
                                           'extraFieldItemWid': extraFieldItem['wid']}
                    extraFieldItemValues.append(extraFieldItemValue)
        # log(extraFieldItemValues)
        # 处理带附加选项的签到
        form['extraFieldItems'] = extraFieldItemValues
    # form['signInstanceWid'] = params['signInstanceWid']
    form['signInstanceWid'] = task['signInstanceWid']
    form['longitude'] = user['lon']
    form['latitude'] = user['lat']
    form['isMalposition'] = task['isMalposition']
    form['abnormalReason'] = user['abnormalReason']
    form['position'] = user['address']
    # print(form)
    return form


# DES加密 (原来的方式加入header会提示今日校园版本太低)
def DESEncrypt(s, key='ST83=@XV'):
    key = key
    iv = b"\x01\x02\x03\x04\x05\x06\x07\x08"
    k = des(key, CBC, iv, pad=None, padmode=PAD_PKCS5)
    encrypt_str = k.encrypt(s)
    return base64.b64encode(encrypt_str).decode()


# 提交签到任务
def submitForm(form):
    extension = {
        "lon": user['lon'],
        "model": "OPPO R11 Plus",
        "appVersion": "8.1.14",
        "systemVersion": "4.4.4",
        "userId": user['username'],
        "systemName": "android",
        "lat": user['lat'],
        "deviceId": str(uuid.uuid1())
    }

    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 4.4.4; OPPO R11 Plus Build/KTU84P) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/33.0.0.0 Safari/537.36 okhttp/3.12.4',
        'CpdailyStandAlone': '0',
        'extension': '1',
        'Cpdaily-Extension': DESEncrypt(json.dumps(extension)),
        'Content-Type': 'application/json; charset=utf-8',
        'Accept-Encoding': 'gzip',
        'Connection': 'Keep-Alive'
    }

    res = session.post(url='https://{host}/wec-counselor-sign-apps/stu/sign/completeSignIn'.format(host=host),headers=headers, data=json.dumps(form))
    #res = session.post(url='https://{host}/wec-counselor-sign-apps/stu/sign/completeSignIn'.format(host=apis['host']),

    message = res.json()['message']
    if message == 'SUCCESS':
        log('自动签到成功')
        sendMessage('自动签到成功', user['email'])
    else:
        log('自动签到失败，原因是：' + message)
        exit(-1)
        # sendMessage('自动签到失败，原因是：' + message, user['email'])


# 发送邮件通知
def sendMessage(msg, email):
    send = email
    if send != '':
        log('正在发送邮件通知。。。')
        res = requests.post(url='http://www.zimo.wiki:8080/mail-sender/sendMail',
                            data={'title': '今日校园自动签到结果通知', 'content': msg, 'to': send})
        code = res.json()['code']
        if code == 0:
            log('发送邮件通知成功。。。')
        else:
            log('发送邮件通知失败。。。')
            log(res.json())


def main():
    data = {
        'sessionToken': sessionToken
    }
    # 不知道为何要去调用login的getModAuthCas方法，在登陆的时候已经调用过了。明天看看
    login.getModAuthCas(data)
    params = getUnSignedTasks()
    # log(params)
    task = getDetailTask(params)
    # log(task)
    form = fillForm(task)
    # log(form)
    submitForm(form)


# 提供给腾讯云函数调用的启动函数
def main_handler(event, context):
    try:
        main()
        return 'success'
    except:
        return 'fail'


if __name__ == '__main__':
    print(main_handler({}, {}))
