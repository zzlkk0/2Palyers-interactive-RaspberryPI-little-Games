#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time, math
import RPi.GPIO as GPIO
from mpu6050 import mpu6050
from RPLCD.i2c import CharLCD

# ———— 参数配置 ————
BUTTON_PIN = 17      # 按钮 GPIO
BUZZER_PIN = 16      # 有源蜂鸣器 GPIO
I2C_ADDR   = 0x27    # LCD I2C 地址（根据实际情况修改）

# 互补滤波参数
ALPHA = 0.4
DT    = 0.01         # 采样间隔（秒）

# ———— 硬件初始化 ————
GPIO.cleanup()
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN,  pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(BUZZER_PIN, GPIO.OUT)
# 确保蜂鸣器初始为关闭
GPIO.output(BUZZER_PIN, GPIO.HIGH)

lcd    = CharLCD('PCF8574', I2C_ADDR, auto_linebreaks=False)
sensor = mpu6050(0x68)
flag=0
def set_buzzer(on: bool):
    """
    控制有源蜂鸣器响 or 不响：
    on=True  → 输出高电平 → 蜂鸣器响
    on=False → 输出低电平 → 蜂鸣器不响
    """
    GPIO.output(BUZZER_PIN, GPIO.LOW if on else GPIO.HIGH)

def beep(pattern):
    """
    pattern: list of (on_duration, off_duration) tuples
    例如 [(0.1,0.1),(0.1,0.1),(0.5,0)] → 短、短、长
    """
    for on_dur, off_dur in pattern:
        set_buzzer(True)
        time.sleep(on_dur)
        set_buzzer(False)
        time.sleep(off_dur)

def wait_for_button():
    lcd.clear()
    if flag==0:
        lcd.write_string(' Press to start ')
    # 等待按下
    while not GPIO.input(BUTTON_PIN):
        time.sleep(0.05)
    # 消抖延时
    time.sleep(0.2)

def game_loop():
    # 1) 等待开始
    wait_for_button()
    global flag
    # 2) 蜂鸣提示：短、短、长
    beep([(0.75,0.5), (0.75,0.5), (0.25,0.03),(0.25,0.03),(0.75,0)])

    # 3) 初始化角度与统计
    roll = pitch = yaw = 0.0
    max_roll = max_pitch = 0.0
    start_t = time.time()

    # 4) 20 秒游戏进行时：LCD 显示计时并更新最大 Roll/Pitch
    while True:
        elapsed = time.time() - start_t
        if elapsed >= 5.0:
            break

        accel = sensor.get_accel_data()
        gyro  = sensor.get_gyro_data()

        # 计算加速度角度
        roll_acc  = math.degrees(math.atan2(accel['y'], accel['z']))
        pitch_acc = math.degrees(math.atan(-accel['x'] / math.sqrt(accel['y']**2 + accel['z']**2)))

        # 互补滤波融合
        roll  = ALPHA * (roll  + gyro['x'] * DT) + (1 - ALPHA) * roll_acc
        pitch = ALPHA * (pitch + gyro['y'] * DT) + (1 - ALPHA) * pitch_acc
        yaw   += gyro['z'] * DT

        # 更新最大绝对值
        max_roll  = max(max_roll,  abs(roll))
        max_pitch = max(max_pitch, abs(pitch))

        # 更新 LCD（第 1 行显示剩余时间）
        lcd.cursor_pos = (0, 0)
        lcd.write_string(f'Time {elapsed:4.1f}s              ')
        time.sleep(DT)

    # 5) 游戏结束，显示结果
    lcd.clear()
    beep([(0.25,0.02),(0.25,0.02),(0.25,0)])
    lcd.write_string('   Game Over!   ')
    time.sleep(1)
    lcd.cursor_pos = (1, 0)
    lcd.write_string(f'R{max_roll:5.1f} P{max_pitch:5.1f}')
    flag=flag+1
    # 6) 等待按钮松开（防止一次长按触发多次）
    while not GPIO.input(BUTTON_PIN):
        time.sleep(0.1)

def main():
    try:
        while True:
            game_loop()
    except KeyboardInterrupt:
        pass
    finally:
        lcd.clear()
        set_buzzer(False)
        GPIO.cleanup()

if __name__ == '__main__':
    main()
