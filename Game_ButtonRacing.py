#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
两人组队按按钮游戏（线程安全 LCD、持续蜂鸣可停止，完整防抖）
当清算界面时要停留5s以防误触
"""
import RPi.GPIO as GPIO
import threading
import time
import random
import queue
from RPLCD.i2c import CharLCD

# ===================== 硬件配置 =====================
BUTTON1_PIN = 17         # 玩家1
BUTTON2_PIN = 24         # 玩家2
BUZZER_PIN  = 16
LED_RED_PIN = 6
LED_GREEN_PIN = 5

LCD_I2C_ADDR = 0x27
LCD_COLUMNS  = 16
LCD_ROWS     = 2

# ===================== 游戏参数 =====================
INITIAL_LIVES = 3
INITIAL_LIGHT_DURATION = 0.7
MIN_LIGHT_DURATION     = 0.3
DELTA_LIGHT            = 0.01
INITIAL_INTERVAL       = 1.0
MIN_INTERVAL           = 0.4
DELTA_INTERVAL         = 0.02
LONG_PRESS_DURATION    = 2.0     # 秒
DEBOUNCE_THRESHOLD     = 0.15    # 秒
END_DISPLAY_DURATION   = 5.0     # 秒，在结束界面停留时长，防止误触

# ===================== 全局状态 =====================
lives   = {1: INITIAL_LIVES, 2: INITIAL_LIVES}
pressed = {1: False, 2: False}
state   = 'waiting'              # waiting/off/green/red/ended

game_start = None
game_end   = None

# --- 线程、锁、队列 ---
state_lock  = threading.Lock()
lcd_lock    = threading.Lock()
reset_event = threading.Event()
buzzer_q    = queue.Queue()

last_press_time = {1: 0, 2: 0}
press_time      = {}

# LCD 对象（稍后初始化)
lcd = None

# ===================== 初始化 =====================

def setup():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    # 按键
    for pin in (BUTTON1_PIN, BUTTON2_PIN):
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    # 输出
    for pin in (LED_RED_PIN, LED_GREEN_PIN, BUZZER_PIN):
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)
    # LCD
    global lcd
    lcd = CharLCD(i2c_expander='PCF8574', address=LCD_I2C_ADDR, port=1,
                  cols=LCD_COLUMNS, rows=LCD_ROWS, charmap='A02')
    with lcd_lock:
        lcd.clear()
        lcd.write_string("Press P1 to Start".ljust(LCD_COLUMNS))
    # 中断
    GPIO.add_event_detect(BUTTON1_PIN, GPIO.BOTH, callback=button_cb, bouncetime=int(DEBOUNCE_THRESHOLD*1000))
    GPIO.add_event_detect(BUTTON2_PIN, GPIO.RISING, callback=button_cb, bouncetime=int(DEBOUNCE_THRESHOLD*1000))
    # 线程
    threading.Thread(target=lcd_thread, daemon=True).start()
    threading.Thread(target=buzzer_thread, daemon=True).start()
    # 初始蜂鸣器停止
    GPIO.output(BUZZER_PIN, GPIO.HIGH)
    print("[INFO] Setup done.")

# ===================== 按键回调 =====================

def button_cb(channel):
    now     = time.time()
    player  = 1 if channel == BUTTON1_PIN else 2
    # 软件去抖
    if now - last_press_time[player] < DEBOUNCE_THRESHOLD:
        return
    last_press_time[player] = now
    val = GPIO.input(channel)

    global state, game_start, game_end
    with state_lock:
        st = state
    # 上升沿
    if val == GPIO.HIGH:
        press_time[player] = now
        print(f"[PRESS] P{player} in {st}")
        # 玩家1 启动或重启逻辑
        if player == 1:
            if st == 'waiting':
                start_game(); return
            if st == 'ended':
                # 结束界面停留，忽略误触
                if game_end and (now - game_end) < END_DISPLAY_DURATION:
                    print(f"[INFO] Ignored P1 press during end display ({now - game_end:.1f}s)")
                    return
                reset_game(); start_game(); return
        # 游戏中按键判定
        if st in ('green', 'red', 'off') and lives[player] > 0 and not pressed[player]:
            if st == 'green':
                pressed[player] = True
                print(f"[OK] P{player} on GREEN")
            else:
                lives[player] -= 1
                pressed[player] = True
                print(f"[PENALTY] P{player} on {st.upper()}  lives={lives[player]}")
    # 下降沿（长按重置）
    elif val == GPIO.LOW and player == 1 and press_time.get(1):
        duration = now - press_time.pop(1)
        if duration >= LONG_PRESS_DURATION:
            print("[RESET] P1 long press")
            reset_event.set()
            reset_game()

# ===================== 游戏控制 =====================

def start_game():
    global state, game_start
    with state_lock:
        state = 'off'
    buzzer_q.put(('times', 3, 0.1, 0.1))
    game_start = time.time()
    threading.Thread(target=game_loop, daemon=True).start()
    print("[INFO] Game started")


def reset_game():
    global lives, state, game_start, game_end
    GPIO.output(LED_RED_PIN, 0); GPIO.output(LED_GREEN_PIN, 0)
    with state_lock:
        lives = {1: INITIAL_LIVES, 2: INITIAL_LIVES}
        state = 'waiting'
    game_start = None; game_end = None
    pressed[1] = pressed[2] = False
    with lcd_lock:
        lcd.clear(); lcd.write_string("Press P1 to Start".ljust(LCD_COLUMNS))
    buzzer_q.put(('stop',))

# ===================== 主循环 =====================

def game_loop():
    reset_event.clear()
    global state, game_end
    light    = INITIAL_LIGHT_DURATION
    interval = INITIAL_INTERVAL
    while not reset_event.is_set() and any(l > 0 for l in lives.values()):
        # 休眠间隔
        with state_lock: state = 'off'
        GPIO.output(LED_RED_PIN, 0); GPIO.output(LED_GREEN_PIN, 0)
        pressed[1] = pressed[2] = False
        t0 = time.time()
        while time.time() - t0 < interval and not reset_event.is_set():
            time.sleep(0.01)
        if reset_event.is_set(): break
        # 灯光阶段
        color = random.choice(['green', 'red'])
        with state_lock: state = color
        pin = LED_GREEN_PIN if color == 'green' else LED_RED_PIN
        GPIO.output(pin, 1)
        print(f"[ROUND] {color.upper()} {light:.2f}s")
        t1 = time.time()
        while time.time() - t1 < light and not reset_event.is_set():
            time.sleep(0.01)
        GPIO.output(pin, 0)
        if reset_event.is_set(): break
        if color == 'green':
            for p in (1, 2):
                if lives[p] > 0 and not pressed[p]:
                    lives[p] -= 1; print(f"[MISS]  P{p} missed GREEN  lives={lives[p]}")
        light    = max(MIN_LIGHT_DURATION, light - DELTA_LIGHT)
        interval = max(MIN_INTERVAL,      interval - DELTA_INTERVAL)

    if not reset_event.is_set():
        with state_lock: state = 'ended'
        game_end = time.time()
        buzzer_q.put(('long2',))
        print(f"[END] Game duration {game_end - game_start:.1f}s")

# ===================== LCD 线程 =====================

def lcd_thread():
    prev = None
    while True:
        with state_lock:
            st = state; l1 = lives[1]; l2 = lives[2]
        if st != prev:
            with lcd_lock: lcd.clear(); prev = st
        with lcd_lock:
            if st == 'waiting':
                lcd.cursor_pos = (0, 0); lcd.write_string("Press P1 to Start".ljust(LCD_COLUMNS))
            elif st in ('off', 'green', 'red') and game_start:
                elapsed = time.time() - game_start
                lcd.cursor_pos = (0, 0); lcd.write_string(f"Time:{elapsed:5.1f}s".ljust(LCD_COLUMNS))
                lcd.cursor_pos = (1, 0); lcd.write_string(f"P1:{l1} P2:{l2}".ljust(LCD_COLUMNS))
            elif st == 'ended':
                total = game_end - game_start if game_start else 0
                lcd.cursor_pos = (0, 0); lcd.write_string("Game Over".ljust(LCD_COLUMNS))
                lcd.cursor_pos = (1, 0); lcd.write_string(f"Time:{total:5.1f}s".ljust(LCD_COLUMNS))
        time.sleep(0.2)

# ===================== 蜂鸣器线程 =====================

def buzzer_thread():
    while True:
        mode, *params = buzzer_q.get()
        if mode == 'times':
            times, dur, iv = params
            for _ in range(times):
                GPIO.output(BUZZER_PIN, 0); time.sleep(dur)
                GPIO.output(BUZZER_PIN, 1); time.sleep(iv)
        elif mode == 'long2':
            GPIO.output(BUZZER_PIN, 0)
            time.sleep(1)
            GPIO.output(BUZZER_PIN, 1); reset_event.clear()
        elif mode == 'stop':
            GPIO.output(BUZZER_PIN, 1)
        elif mode == 'long':
            dur, = params; GPIO.output(BUZZER_PIN, 0); time.sleep(dur); GPIO.output(BUZZER_PIN, 1)

# ===================== 清理 =====================

def cleanup():
    GPIO.output(LED_RED_PIN, 0); GPIO.output(LED_GREEN_PIN, 0); GPIO.output(BUZZER_PIN, 0)
    GPIO.cleanup()

# ===================== 主入口 =====================
if __name__ == '__main__':
    try:
        setup()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()
