# КЕША 3.1 (aka Jarvis)
"""
    Создано Хауди Хо, изменено YarBurArt
    ВНИМАНИЕ!!!
    Пока что это максимально сырой прототип.
    Позже будет опубликована нормальная версия с удобной установкой и поддержкой всего чего только можно.
    А пока что, код ниже к вашим услугам, сэр :)

    @TODO:
   -2. Визуализация через gif или Blender
   -1. Подключить модель animemajg или апи character.ai
    0. Адекватная архитектура кода, собрать всё и переписать from the ground up.
    1. Задержка воспроизведения звука на основе реальной длительности .wav файла (прогружать при запуске?)
    2. Speech to intent?
    3. Отключать self listening protection во время воспроизведения с наушников.
    4. Указание из списка или по имени будет реализовано позже.
"""

import os
import random

import pvporcupine
import simpleaudio as sa
from pvrecorder import PvRecorder
from rich import print
import vosk
import sys
import queue
import json
import struct
import config
from fuzzywuzzy import fuzz
import tts
import datetime
#from num2t4ru import num2text
import subprocess
import time

import autopc

from transformers import AutoModelForCausalLM, AutoTokenizer
from deep_translator import GoogleTranslator

from ctypes import POINTER, cast
if sys.platform == 'win32':
    from comtypes import CLSCTX_ALL, COMObject
    from pycaw.pycaw import (
        AudioUtilities,
        IAudioEndpointVolume
    )

# import openai
from gpytranslate import SyncTranslator

CDIR = os.getcwd()

# init translator
t = SyncTranslator()

# init openai
# openai.api_key = config.OPENAI_TOKEN

# init anime gpt2 tuned
tokenizer = AutoTokenizer.from_pretrained('facebook/opt-125m')
model_gpt = AutoModelForCausalLM.from_pretrained('facebook/opt-125m')

# template's translation
translator = GoogleTranslator(source='ru', target='en')
translator1 = GoogleTranslator(source='en', target='ru')

# PORCUPINE
try:
    porcupine = pvporcupine.create(
        access_key=config.PICOVOICE_TOKEN,
        keywords=['jarvis'],
        sensitivities=[1]
    )
    # print(pvporcupine.KEYWORDS)
    is_vosk_wake_word = False
    k_frame_length = porcupine.frame_length
except ValueError:
    is_vosk_wake_word = True
    k_frame_length = 4096

# VOSK
model = vosk.Model(r"models/vosk-model-small-ru-0.22")
samplerate = 16000
device = config.MICROPHONE_INDEX
kaldi_rec = vosk.KaldiRecognizer(model, samplerate)
q = queue.Queue()


# debug warn
class StdoutInterceptor:
    def __init__(self):
        self.stdout = sys.stdout

    def flush(self):
        pass

    def write(self, s):
        if not s == "[WARN] Overflow - reader is not reading fast enough.":
            self.stdout.write(s)


sys.stdout = StdoutInterceptor()


def gpt_answer(message: str) -> str:
    message = translator.translate(message)
    inputs = tokenizer.encode(message, return_tensors='pt')
    outputs = model_gpt.generate(inputs, max_length=100, do_sample=True)
    message = tokenizer.decode(outputs[0], skip_special_tokens=True)
    return translator1.translate(message)


# play(f'{CDIR}\\sound\\ok{random.choice([1, 2, 3, 4])}.wav')
def play(phrase, wait_done=True):
    global recorder
    if sys.platform == 'win32':
        filename = f"{CDIR}\\sound\\"
    else:
        filename = f"{CDIR}/sound/"

    if phrase == "greet":  # for py 3.8
        filename += f"greet{random.choice([1, 2, 3])}.wav"
    elif phrase == "ok":
        filename += f"ok{random.choice([1, 2, 3])}.wav"
    elif phrase == "not_found":
        filename += "not_found.wav"
    elif phrase == "thanks":
        filename += "thanks.wav"
    elif phrase == "run":
        filename += "run.wav"
    elif phrase == "stupid":
        filename += "stupid.wav"
    elif phrase == "ready":
        filename += "ready.wav"
    elif phrase == "off":
        filename += "off.wav"

    if wait_done:
        recorder.stop()

    wave_obj = sa.WaveObject.from_wave_file(filename)
    wave_obj.play()

    if wait_done:
        # play_obj.wait_done()
        # time.sleep((len(wave_obj.audio_data) / wave_obj.sample_rate) + 0.5)
        # print("END")
        time.sleep(0.8)
        recorder.start()


def q_callback(indata, frames, time, status):
    if status:
        print(status, file=sys.stderr)
    q.put(bytes(indata))


def va_respond(voice: str):
    global recorder
    print(f"Распознано: {voice}")

    cmd = recognize_cmd(filter_cmd(voice))

    print(cmd)

    if len(cmd['cmd'].strip()) <= 0:
        return False
    elif cmd['percent'] < 70 or cmd['cmd'] not in config.VA_CMD_LIST.keys():
        # play("not_found")
        # tts.va_speak("Что?")
        if fuzz.ratio(voice.join(voice.split()[:1]).strip(), "скажи") > 75:
            gpt_result = gpt_answer(voice)
            # gpt_result = "нет"
            recorder.stop()
            tts.va_speak(gpt_result)
            time.sleep(1)
            recorder.start()
            return False
        else:
            play("not_found")
            time.sleep(1)

        return False
    else:
        execute_cmd(cmd['cmd'], voice)
        return True


def filter_cmd(raw_voice: str):
    cmd = raw_voice

    for x in config.VA_ALIAS:
        cmd = cmd.replace(x, "").strip()

    for x in config.VA_TBR:
        cmd = cmd.replace(x, "").strip()

    return cmd


def recognize_cmd(cmd: str):
    rc = {'cmd': '', 'percent': 0}
    for c, v in config.VA_CMD_LIST.items():

        for x in v:
            vrt = fuzz.ratio(cmd, x)
            if vrt > rc['percent']:
                rc['cmd'] = c
                rc['percent'] = vrt

    return rc


def execute_cmd(cmd: str, voice: str):
    if cmd == 'help':
        # help
        text = "Я умею: ..."
        text += "произносить время ..."
        text += "рассказывать анекдоты ..."
        text += "и открывать браузер"
        tts.va_speak(text)
        pass
    elif cmd == 'ctime':
        # current time
        now = datetime.datetime.now()
        text = "Сейч+ас " + str(now.hour) + " " + str(now.minute)
        tts.va_speak(text)

    elif cmd == 'joke':
        jokes = ['Как смеются программисты? ... ехе ехе ехе',
                 'ЭсКьюЭль запрос заходит в бар, подходит к двум столам и спрашивает .. «м+ожно присоединиться?»',
                 'Программист это машина для преобразования кофе в код']

        play("ok", True)

        tts.va_speak(random.choice(jokes))

    elif cmd == 'open_browser':
        autopc.run_app("yan")
        play("ok")

    elif cmd == 'open_youtube':
        autopc.run_browser("https://www.youtube.com")
        play("ok")

    elif cmd == 'open_google':
        autopc.run_browser()
        play("ok")

    elif cmd == 'music':
        autopc.run_browser("https://music.yandex.ru/radio")
        play("ok")

    elif cmd == 'music_off':
        subprocess.Popen([f'{CDIR}\\custom-commands\\Stop music.exe'])
        time.sleep(0.2)
        play("ok")

    elif cmd == 'music_save':
        subprocess.Popen([f'{CDIR}\\custom-commands\\Save music.exe'])
        time.sleep(0.2)
        play("ok")

    elif cmd == 'music_next':
        subprocess.Popen([f'{CDIR}\\custom-commands\\Next music.exe'])
        time.sleep(0.2)
        play("ok")

    elif cmd == 'music_prev':
        subprocess.Popen([f'{CDIR}\\custom-commands\\Prev music.exe'])
        time.sleep(0.2)
        play("ok")

    elif cmd == 'sound_off':
        play("ok", True)

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        volume.SetMute(1, None)

    elif cmd == 'sound_on':
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        volume.SetMute(0, None)

        play("ok")

    elif cmd == 'thanks':
        play("thanks")

    elif cmd == 'stupid':
        play("stupid")

    elif cmd == 'gaming_mode_on':
        play("ok")
        autopc.run_game("fortnite")
        play("ready")

    elif cmd == 'gaming_mode_off':
        play("ok")
        subprocess.check_call([f'{CDIR}\\custom-commands\\Switch back to workspace.exe'])
        play("ready")

    elif cmd == 'switch_to_headphones':
        play("ok")
        subprocess.check_call([f'{CDIR}\\custom-commands\\Switch to headphones.exe'])
        time.sleep(0.5)
        play("ready")

    elif cmd == 'switch_to_dynamics':
        play("ok")
        subprocess.check_call([f'{CDIR}\\custom-commands\\Switch to dynamics.exe'])
        time.sleep(0.5)
        play("ready")

    elif cmd == 'off':
        play("off", True)

        porcupine.delete()
        exit(0)


# `-1` is the default input audio device.
recorder = PvRecorder(
        device_index=config.MICROPHONE_INDEX,
        frame_length=k_frame_length
    )
recorder.start()
print('Using device: %s' % recorder.selected_device)

print(f"Jarvis (v3.1) начал свою работу ...")
play("run")
time.sleep(0.5)

ltc = time.time() - 1000

while True:
    try:
        pcm = recorder.read()
        sp_i = struct.pack("h" * len(pcm), *pcm)
        if porcupine and not is_vosk_wake_word:
            keyword_index = porcupine.process(pcm)
            if keyword_index >= 0:
                recorder.stop()
                play("greet", True)
                print("Yes, sir.")
                recorder.start()  # prevent self recording
                ltc = time.time()
        elif is_vosk_wake_word:
             if kaldi_rec.AcceptWaveform(sp):
                result = json.loads(kaldi_rec.Result())
                text = result.get("text", "").lower()
                print(f"Vosk: {text}")
                if WAKE_WORD in text:
                    recorder.stop()
                    play("greet", True)
                    print("Yes, sir.")
                    recorder.start()
                    ltc = time.time()

        while time.time() - ltc <= 10:
            pcm = recorder.read()
            sp = struct.pack("h" * len(pcm), *pcm)

            if kaldi_rec.AcceptWaveform(sp):
                if va_respond(json.loads(kaldi_rec.Result())["text"]):
                    ltc = time.time()
            
            if time.time() - ltc > 10:
                kaldi_rec.Result()
                print(1)
                break

        if time.time() - ltc > 10:
            kaldi_rec.Result()
            ltc = time.time() - 9


    except Exception as err:
        print(f"Unexpected {err=}, {type(err)=}")
        raise
