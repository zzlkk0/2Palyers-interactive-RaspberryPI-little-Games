#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 说明：循迹模块控制力训练游戏

import RPi.GPIO as GPIO
import time
import threading

TRACK_PIN   = 18  # 循迹传感器引脚
BUTTON_PIN  = 17 # 按钮输入引脚
BUZZER_PIN  = 16 # 有源蜂鸣器输出引脚

# 游戏参数
MAX_HEARTS = 5    # 最大心跳次数（偏离次数）


def setup():
    GPIO.cleanup()
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    # 循迹传感器：输入，上拉
    GPIO.setup(TRACK_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    # 按钮：输入，下拉（按下接 3.3V）
    GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    # 蜂鸣器：输出
    GPIO.setup(BUZZER_PIN, GPIO.OUT)
    GPIO.output(BUZZER_PIN, GPIO.HIGH)

def cleanup():
    GPIO.cleanup()


def wait_for_button():
    """
    等待按钮被按下后返回。
    """
    while True:
        if GPIO.input(BUTTON_PIN) == GPIO.HIGH:
            # 消抖
            time.sleep(0.05)
            if GPIO.input(BUTTON_PIN) == GPIO.HIGH:
                return
        time.sleep(0.1)


def beep(times=1, duration=0.1):
    """
    蜂鸣器响 times 次，每次持续 duration 秒。
    """
    for _ in range(times):
        GPIO.output(BUZZER_PIN, GPIO.LOW)
        time.sleep(duration)
        GPIO.output(BUZZER_PIN, GPIO.HIGH)
        time.sleep(duration)
def thread_beep(times=1, duration= 0.1):
    beep(times,duration)
def main():
    setup()
    try:
        while True:
            print("等待按下按钮开始游戏...")
            wait_for_button()

            # 开始游戏提示：蜂鸣器连响三下
            print("游戏开始！")
            beep(times=3, duration=0.2)

            hearts = MAX_HEARTS
            prev_on_line = True  # 用于检测从黑线到白线的边沿

            # 游戏主循环
            while hearts > 0:
                sensor = GPIO.input(TRACK_PIN)
                if sensor == GPIO.LOW and prev_on_line:
                    # 检测到白线偏离，丢失 1 心
                    hearts -= 1
                    print(f"偏离黑线！心跳剩余：{hearts}")
                    prev_on_line = False
                    if hearts >=1:
                      threading.Thread(target=thread_beep,args=(2,0.1),daemon=True).start()
                elif sensor == GPIO.HIGH:
                    # 恢复在黑线，重置边沿检测
                    prev_on_line = True

                time.sleep(0.05)

            # 游戏失败
            print("游戏失败！心跳用尽。")
            GPIO.output(BUZZER_PIN, GPIO.LOW)
            
            time.sleep(1.5)
            GPIO.output(BUZZER_PIN, GPIO.HIGH)

            # 等待再次按键重启
            print("按下按钮可重新开始游戏。")
            wait_for_button()
            time.sleep(0.2)

    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == '__main__':
    main()
