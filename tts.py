#coding=utf-8

'''
requires Python 3.6 or later

pip install asyncio
pip install websockets

'''

import asyncio
import websockets
import uuid
import json
import gzip
import copy

import pygame

import tkinter as tk
from tkinter import ttk
import time

from threading import Thread




MESSAGE_TYPES = {11: "audio-only server response", 12: "frontend server response", 15: "error message from server"}
MESSAGE_TYPE_SPECIFIC_FLAGS = {0: "no sequence number", 1: "sequence number > 0",
                               2: "last message from server (seq < 0)", 3: "sequence number < 0"}
MESSAGE_SERIALIZATION_METHODS = {0: "no serialization", 1: "JSON", 15: "custom type"}
MESSAGE_COMPRESSIONS = {0: "no compression", 1: "gzip", 15: "custom compression method"}

appid = "3790499700"
token = "JnCmf8tlCO7w-989ZXbhwrjCvHfeNBYP"
cluster = "volcano_tts"
voice_type = "BV700_V2_streaming"
host = "openspeech.bytedance.com"
api_url = f"wss://{host}/api/v1/tts/ws_binary"


# version: b0001 (4 bits)
# header size: b0001 (4 bits)
# message type: b0001 (Full client request) (4bits)
# message type specific flags: b0000 (none) (4bits)
# message serialization method: b0001 (JSON) (4 bits)
# message compression: b0001 (gzip) (4bits)
# reserved data: 0x00 (1 byte)
default_header = bytearray(b'\x11\x10\x11\x00')

request_json = {
    "app": {
        "appid": appid,
        "token": "access_token",
        "cluster": cluster
    },
    "user": {
        "uid": "388808087185088"
    },
    "audio": {
        "voice_type": "xxx",
        "encoding": "mp3",
        "speed_ratio": 1.0,
        "volume_ratio": 1.0,
        "pitch_ratio": 1.0,
    },
    "request": {
        "reqid": "xxx",
        "text": "xxx",
        "text_type": "plain",
        "operation": "xxx"
    }
}


async def test_submit(text):
    submit_request_json = copy.deepcopy(request_json)
    submit_request_json["audio"]["voice_type"] = voice_type
    submit_request_json["request"]["reqid"] = str(uuid.uuid4())
    submit_request_json["request"]["operation"] = "submit"
    submit_request_json["request"]["text"] = text

    payload_bytes = str.encode(json.dumps(submit_request_json))
    payload_bytes = gzip.compress(payload_bytes)  # if no compression, comment this line
    full_client_request = bytearray(default_header)
    full_client_request.extend((len(payload_bytes)).to_bytes(4, 'big'))  # payload size(4 bytes)
    full_client_request.extend(payload_bytes)  # payload
    print("\n------------------------ test 'submit' -------------------------")
    print("request json: ", submit_request_json)
    print("\nrequest bytes: ", full_client_request)
    file_to_save = open("test_submit.mp3", "wb")
    header = {"Authorization": f"Bearer; {token}"}
    async with websockets.connect(api_url, extra_headers=header, ping_interval=None) as ws:
        await ws.send(full_client_request)
        while True:
            res = await ws.recv()
            done = parse_response(res, file_to_save)
            if done:
                file_to_save.close()
                break
        print("\nclosing the connection...")


async def test_query(text):
    query_request_json = copy.deepcopy(request_json)
    query_request_json["audio"]["voice_type"] = voice_type
    query_request_json["request"]["reqid"] = str(uuid.uuid4())
    query_request_json["request"]["operation"] = "query"
    query_request_json["request"]["text"] = text
    payload_bytes = str.encode(json.dumps(query_request_json))
    payload_bytes = gzip.compress(payload_bytes)  # if no compression, comment this line
    full_client_request = bytearray(default_header)
    full_client_request.extend((len(payload_bytes)).to_bytes(4, 'big'))  # payload size(4 bytes)
    full_client_request.extend(payload_bytes)  # payload
    print("\n------------------------ test 'query' -------------------------")
    print("request json: ", query_request_json)
    print("\nrequest bytes: ", full_client_request)
    file_to_save = open("test_query.mp3", "wb")
    header = {"Authorization": f"Bearer; {token}"}
    async with websockets.connect(api_url, extra_headers=header, ping_interval=None) as ws:
        await ws.send(full_client_request)
        res = await ws.recv()
        parse_response(res, file_to_save)
        file_to_save.close()
        print("\nclosing the connection...")


def parse_response(res, file):
    print("--------------------------- response ---------------------------")
    # print(f"response raw bytes: {res}")
    protocol_version = res[0] >> 4
    header_size = res[0] & 0x0f
    message_type = res[1] >> 4
    message_type_specific_flags = res[1] & 0x0f
    serialization_method = res[2] >> 4
    message_compression = res[2] & 0x0f
    reserved = res[3]
    header_extensions = res[4:header_size*4]
    payload = res[header_size*4:]
    print(f"            Protocol version: {protocol_version:#x} - version {protocol_version}")
    print(f"                 Header size: {header_size:#x} - {header_size * 4} bytes ")
    print(f"                Message type: {message_type:#x} - {MESSAGE_TYPES[message_type]}")
    print(f" Message type specific flags: {message_type_specific_flags:#x} - {MESSAGE_TYPE_SPECIFIC_FLAGS[message_type_specific_flags]}")
    print(f"Message serialization method: {serialization_method:#x} - {MESSAGE_SERIALIZATION_METHODS[serialization_method]}")
    print(f"         Message compression: {message_compression:#x} - {MESSAGE_COMPRESSIONS[message_compression]}")
    print(f"                    Reserved: {reserved:#04x}")
    if header_size != 1:
        print(f"           Header extensions: {header_extensions}")
    if message_type == 0xb:  # audio-only server response
        if message_type_specific_flags == 0:  # no sequence number as ACK
            print("                Payload size: 0")
            return False
        else:
            sequence_number = int.from_bytes(payload[:4], "big", signed=True)
            payload_size = int.from_bytes(payload[4:8], "big", signed=False)
            payload = payload[8:]
            print(f"             Sequence number: {sequence_number}")
            print(f"                Payload size: {payload_size} bytes")
        file.write(payload)
        if sequence_number < 0:
            return True
        else:
            return False
    elif message_type == 0xf:
        code = int.from_bytes(payload[:4], "big", signed=False)
        msg_size = int.from_bytes(payload[4:8], "big", signed=False)
        error_msg = payload[8:]
        if message_compression == 1:
            error_msg = gzip.decompress(error_msg)
        error_msg = str(error_msg, "utf-8")
        print(f"          Error message code: {code}")
        print(f"          Error message size: {msg_size} bytes")
        print(f"               Error message: {error_msg}")
        return True
    elif message_type == 0xc:
        msg_size = int.from_bytes(payload[:4], "big", signed=False)
        payload = payload[4:]
        if message_compression == 1:
            payload = gzip.decompress(payload)
        print(f"            Frontend message: {payload}")
    else:
        print("undefined message type!")
        return True

def show_popup(master):
        # 获取主窗口的位置和尺寸
    master_x = master.winfo_x()
    master_y = master.winfo_y()
    master_width = master.winfo_width()
    master_height = master.winfo_height()
    # 创建一个新的顶层窗口作为弹窗
    popup = tk.Toplevel(master)
    popup.title("弹窗")
    
    # 设置弹窗的尺寸
    popup.geometry("300x200")

    # 计算弹窗的位置，使其居中于主窗口
    popup_x = master_x + (master_width // 2) - (300 // 2)
    popup_y = master_y + (master_height // 2) - (200 // 2)
    popup.geometry(f"300x200+{popup_x}+{popup_y}")

    # 创建一个标签
    label = tk.Label(popup, text="运行完毕")
    label.pack(padx=20, pady=20)

    # 创建一个关闭按钮
    close_button = tk.Button(popup, text="O", command=popup.destroy)
    close_button.pack(pady=10)

def on_submit():
    input_text = entry.get()
    print(f"输入的文本是: {input_text}")
    
    # 在新线程中运行 asyncio 事件循环，以防止阻塞主线程
    def run_asyncio_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(test_submit(input_text))
        loop.run_until_complete(test_query(input_text))
        loop.run_until_complete(play_mp3("test_query.mp3"))


    # Thread(target=run_asyncio_loop).start()
    # 创建并启动线程
    asyncio_thread = Thread(target=run_asyncio_loop)
    asyncio_thread.start()

    # 等待线程完成（可选）
    asyncio_thread.join()  # 等待线程运行完成

    # 线程运行完成后，继续主线程的操作
    print("Asyncio thread has completed.")
    show_popup(root)



async def play_mp3(file_path):
    pygame.mixer.init()
    pygame.mixer.music.load(file_path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)
      # 播放结束后释放资源

    pygame.mixer.music.stop()
    pygame.mixer.quit()
    pygame.quit()

#获取当前时间
def get_current_time(self):
    current_time = time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(time.time()))
    return current_time

# 配置页面
def save_config():
    # 在这里编写保存配置的逻辑
    print("保存配置")

def show_config_window():
    config_window = tk.Toplevel(root)
    config_window.title("配置页面")

    # 添加配置选项，例如：
    label = tk.Label(config_window, text="配置项1:")
    label.pack(pady=10)

    entry = tk.Entry(config_window)
    entry.pack()

    save_button = tk.Button(config_window, text="保存配置", command=save_config)
    save_button.pack(pady=20)

def save_settings():
    selected_option1 = combobox1.get()
    selected_option2 = combobox2.get()

    # 在这里可以根据选择的选项执行相应的操作或保存设置
    print("Option 1 selected:", selected_option1)
    print("Option 2 selected:", selected_option2)

def open_settings():
    settings_window = tk.Toplevel(root)
    settings_window.title("Settings")
    # 添加设置页面的内容和控件
    # 添加第一个下拉框
    label1 = tk.Label(settings_window, text="Parameter 1:")
    label1.pack()

    options1 = ["Option 1", "Option 2", "Option 3"]
    combobox1 = ttk.Combobox(settings_window, values=options1)
    combobox1.pack()

    # 添加第二个下拉框
    label2 = ttk.Label(settings_window, text="Parameter 2:")
    label2.pack()

    options2 = ["Choice A", "Choice B", "Choice C"]
    combobox2 = tk.Combobox(settings_window, values=options2)
    combobox2.pack()

    # 添加保存按钮
    save_button = tk.Button(settings_window, text="Save Settings", command=save_settings)
    save_button.pack()
    # # 添加复选框
    # check_var1 = tk.IntVar()
    # check_var2 = tk.IntVar()

    # checkbutton1 = tk.Checkbutton(settings_window, text="Option 1", variable=check_var1)
    # checkbutton1.pack()

    # checkbutton2 = tk.Checkbutton(settings_window, text="Option 2", variable=check_var2)
    # checkbutton2.pack()

if __name__ == '__main__':
        # 创建 Tkinter 主窗口
    root = tk.Tk()
    root.title("主窗口")
    # 设置主窗口的尺寸和初始位置
    window_width = 400
    window_height = 300
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width // 2) - (window_width // 2)  # 计算窗口的水平位置
    y = (screen_height // 2) - (window_height // 2)  # 计算窗口的垂直位置
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    root.resizable(False, False)#宽高能否改变

    # 创建菜单栏
    menubar = tk.Menu(root)
    root.config(menu=menubar)

    # 添加菜单选项
    file_menu = tk.Menu(menubar, tearoff=0)
    menubar.add_cascade(label="Option", menu=file_menu)
    file_menu.add_command(label="Settings", command=open_settings)

    # 创建一个标签
    label = tk.Label(root, text="请输入内容：")
    label.grid(row=0, column=0, pady=(50, 10))

    # 创建一个文本框
    entry = tk.Entry(root, width=30)
    entry.grid(row=1, column=0, pady=(0, 10))

    # 创建一个按钮
    button = tk.Button(root, text="确定", command=on_submit)
    button.grid(row=2, column=0, pady=20)

    # 将主窗口的列设置为居中
    root.grid_columnconfigure(0, weight=1)
    
    # # 添加按钮来打开配置页面
    # config_button = tk.Button(root, text="打开配置页面", command=show_config_window)
    # config_button.grid(row=0,column=0,pady=20)

    
    # 运行 Tkinter 主循环
    root.mainloop()


