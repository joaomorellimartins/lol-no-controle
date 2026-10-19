"""League of Legends com controle PS5 (DualSense) -- motor em Python.

Le o DualSense direto por HID (touchpad, gatilhos, luz e vibracao) e gera teclado + mouse.
So atua quando o LoL (jogo ou cliente) esta em foco. Cada aperto gera UMA acao.

MAPA (preset "Keyboard (WASD)" do jogo; as teclas sao lidas do input.ini do LoL)
  Stick esquerdo ....... W A S D (andar)
  Stick direito ........ MODO MIRA: cursor = personagem + DIRECAO do stick, a distancia fixa (fica onde mirou)
                         solto: o cursor vai para frente do personagem, no rumo em que ele anda (WASD)
  R3 (clicar stick dir). toque curto = alterna MIRA <-> LIVRE (LIVRE = cursor solto, loja/menus)
  R3 SEGURADO 1 s ...... CALIBRAR (camera travada, mouse fisico em cima do personagem) -- ou Create + R3
  R1 ................... autoataque: stick direito solto = atacar-mover nos pes (o JOGO ataca o inimigo mais
                         perto de voce); stick direito apontando = ataca o mais perto de onde aponta
  Bola ................. liga/desliga "mirar so em campeoes" do jogo (Tab): bipe agudo = ligado, grave = desligado
  L1 / L2 / R2 / X ..... habilidades 1 / 2 / 3 / 4
  (desligado) SEGURANDO habilidade/autoataque: stick direito mira, giroscopio ajusta fino, vibra no
                         limite do alcance -- religar com MIRA_AO_SEGURAR / GIRO_ATIVO / VIBRA_BORDA.
  L3 SEGURADO + L1/L2/R2/X ... subir habilidade 1/2/3/4 (Ctrl+Q/W/E/R)
  L3 (toque sozinho) ... clique direito
  Quadrado / Triangulo . feiticos 5 / 6
  Direcional ........... esquerda = item 7 | direita = item 8 | cima = 9 (ward) | baixo = B (voltar a base)
  Touchpad (arrastar) .. clique esquerdo + movimento sobre o MINIMAPA, partindo de onde a camera esta
  Options .............. Esc        Create (tocar) .... loja
  Create + clique touchpad ... travar/destravar camera
  Create + Options ..... PAUSA / RETOMA (vale mesmo fora do jogo)
"""
import configparser
import ctypes
import ctypes.wintypes as wt
import json
import math
import os
import re
import ssl
import struct
import sys
import threading
import time
import urllib.request
import zlib
import logging

import hid

# ----------------------------- AJUSTES (mexa aqui) -----------------------------
VEL_LIVRE_PX_S   = 2600    # velocidade do cursor no modo LIVRE com o stick no maximo (pixels/s)
ZONA_MORTA       = 0.18    # tremida do stick ignorada (modo livre)
ZONA_WASD        = 0.40    # quanto empurrar o stick esquerdo para virar W/A/S/D
RAIO_X           = 600     # modo mira: alcance horizontal a partir do personagem (pixels)
RAIO_Y           = 380     # modo mira: alcance vertical
ZONA_MORTA_MIRA  = 0.25    # stick precisa passar disso para mirar
MIRA_POR_DIRECAO = True    # stick direito so da a DIRECAO: o cursor fica a uma distancia fixa (MIRA_DISTANCIA)
MIRA_DISTANCIA   = 0.75    # distancia fixa, como fracao de RAIO_X/RAIO_Y
MIRA_SEGUE_MOVIMENTO = True  # stick direito solto: o cursor vai para frente do personagem, no rumo em que ele anda
AUTOATAQUE_MAIS_PERTO = True # R1 com stick direito solto: atacar-mover nos pes = o jogo ataca o inimigo mais perto
BOLA_SO_CAMPEOES = True      # Bola liga/desliga "mirar so em campeoes" do jogo (Tab)
# --- mira de habilidade (segurar o botao da habilidade ou do autoataque) -- DESLIGADA (testada em 18/10/2026,
#     funcionou mas nao agradou; o codigo fica para religar trocando as chaves abaixo para True)
MIRA_AO_SEGURAR  = False   # segurando habilidade/autoataque, o stick direito mira mesmo no modo LIVRE
GIRO_ATIVO       = False   # inclinar o controle ajusta o cursor enquanto segura habilidade/autoataque
GIRO_PX_GRAU     = 10.0    # pixels por grau de giro (maior = mais sensivel)
GIRO_INV_X       = False   # inverte o sentido horizontal do giroscopio
GIRO_INV_Y       = False   # inverte o sentido vertical do giroscopio
GIRO_ZONA_GRAU_S = 1.5     # ignora giro mais lento que isso (tremor da mao/deriva)
VIBRA_BORDA      = False   # toque de vibracao quando o stick chega no limite do alcance
VOLTA_S          = 0       # segundos PARADO (stick solto e nenhum botao apertado) para o cursor voltar ao
                           # personagem; enquanto isso ele fica onde voce apontou (0 = nunca volta)
MINIMAPA         = (0.7927, 0.6296, 0.9906, 0.9815)  # minimapa como fracao da janela: x0,y0,x1,y1
TOUCH_X0, TOUCH_X1 = 420, 1500                       # (reserva) faixa do touchpad usada se a camera nao for achada
TOUCH_GANHO      = 0.28    # arrastar: pixels do minimapa por pixel do touchpad (maior = mais rapido)
LEFT_STICK       = "auto"  # stick esquerdo: "auto" = WASD se W/A/S/D estiverem LIVRES no jogo, senao setas
                           # (camera); "wasd" ou "setas" forcam um dos dois.
INPUT_INI        = r"C:\Riot Games\League of Legends\Config\input.ini"   # atalhos do proprio jogo (dono das teclas)
PRESET           = "wasd"  # preset de teclas do jogo: "wasd" = Keyboard (WASD) (habilidades 1-4, feiticos 5-6,
                           # itens 7-8, ward 9, W/A/S/D andam); "classico" = Q/W/E/R...; "auto" = ler do game.cfg.
                           # (O jogo so grava o preset no arquivo depois, por isso nao da para confiar so nele.)
ALVOS            = ("league of legends.exe", "leagueclientux.exe")
COR_MIRA, COR_LIVRE, COR_PAUSA = (0, 255, 60), (0, 90, 255), (160, 0, 255)
# --- luz e vibracao (dados da API oficial do cliente: https://127.0.0.1:2999, somente leitura)
LUZ_VIDA         = True    # barra de luz = vida (verde -> amarelo -> vermelho; pisca abaixo de 25%)
LEDS_PONTOS      = True    # LEDs sob o touchpad = pontos de habilidade para gastar (ate 5)
VIBRA_DANO       = True    # vibra ao tomar dano (mais forte quanto maior o dano)
VIBRA_EVENTOS    = True    # vibra ao morrer, renascer e ganhar ponto de habilidade
DANO_MIN         = 0.03    # fracao da vida maxima perdida para vibrar
# -------------------------------------------------------------------------------

AQUI = os.path.dirname(os.path.abspath(__file__))
ARQ_CALIB = os.path.join(AQUI, "calibracao.ini")
logging.basicConfig(filename=os.path.join(AQUI, "lol_controle.log"), level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("lol")

# ------------------------------- Windows (ctypes) ------------------------------
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    user32.SetProcessDPIAware()

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]


class _INPUTU(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("u", _INPUTU)]


user32.GetForegroundWindow.restype = wt.HWND
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.SendInput.argtypes = [wt.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
kernel32.CloseHandle.argtypes = [wt.HANDLE]

VK = {"esc": 0x1B, "escape": 0x1B, "ctrl": 0xA2, "alt": 0xA4, "shift": 0xA0, "space": 0x20, "tab": 0x09,
      "return": 0x0D, "enter": 0x0D, "`": 0xC0, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
      "backspace": 0x08, "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
      "pageup": 0x21, "pagedown": 0x22}
ESTENDIDAS = {0x26, 0x28, 0x25, 0x27, 0x2D, 0x2E, 0x24, 0x23, 0x21, 0x22}


def vk_de(k):
    """Nome da tecla -> codigo virtual (None se nao souber)."""
    k = k.lower()
    if k in VK:
        return VK[k]
    if len(k) == 1 and (k.isalnum()):
        return ord(k.upper())
    m = re.fullmatch(r"f(\d{1,2})", k)
    if m and 1 <= int(m.group(1)) <= 12:
        return 0x6F + int(m.group(1))
    return None


def tecla(k, baixo):
    vk = vk_de(k)
    if vk is None:
        return
    scan = user32.MapVirtualKeyW(vk, 0)
    flags = (0 if baixo else 2) | (1 if vk in ESTENDIDAS else 0)
    inp = INPUT(type=1, u=_INPUTU(ki=KEYBDINPUT(vk, scan, flags, 0, 0)))
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


# ---------------- captura da tela (so para achar o retangulo da camera no minimapa) ----------------
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
user32.GetDC.restype = ctypes.c_void_p
user32.GetDC.argtypes = [ctypes.c_void_p]
user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
gdi32.CreateCompatibleBitmap.restype = ctypes.c_void_p
gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.restype = ctypes.c_void_p
gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.BitBlt.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         ctypes.c_void_p, ctypes.c_int, ctypes.c_int, wt.DWORD]
gdi32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wt.UINT, wt.UINT, ctypes.c_void_p,
                            ctypes.c_void_p, wt.UINT]
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
gdi32.DeleteDC.argtypes = [ctypes.c_void_p]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


def capturar(x, y, w, h):
    """Copia um retangulo da tela (BGRA, de cima para baixo). Devolve bytes ou None."""
    hdc = user32.GetDC(None)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    antigo = gdi32.SelectObject(mdc, bmp)
    try:
        if not gdi32.BitBlt(mdc, 0, 0, w, h, hdc, x, y, 0x00CC0020 | 0x40000000):
            return None
        bi = BITMAPINFOHEADER()
        bi.biSize, bi.biWidth, bi.biHeight, bi.biPlanes, bi.biBitCount = 40, w, -h, 1, 32
        buf = ctypes.create_string_buffer(w * h * 4)
        if not gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0):
            return None
        return buf.raw
    finally:
        gdi32.SelectObject(mdc, antigo)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mdc)
        user32.ReleaseDC(None, hdc)


_TAB_BRANCO = bytes(1 if (v & 0xE0) == 0xE0 else 0 for v in range(256))


def _grupos(valores):
    """Agrupa numeros consecutivos (linhas/colunas vizinhas da mesma borda) e devolve o centro de cada grupo."""
    grupos, atual = [], []
    for v in sorted(set(valores)):
        if atual and v - atual[-1] > 2:
            grupos.append(sum(atual) / len(atual))
            atual = []
        atual.append(v)
    if atual:
        grupos.append(sum(atual) / len(atual))
    return grupos


def _eixo(bordas, tam, lo, hi):
    """Centro da camera num eixo a partir das bordas brancas vistas (0, 1 ou 2). Se so uma borda aparece,
    a outra esta fora do mapa; o tamanho fixo do retangulo diz de que lado."""
    if not bordas:
        return None, None
    if len(bordas) >= 2:
        for i in range(len(bordas)):
            for j in range(i + 1, len(bordas)):
                if abs((bordas[j] - bordas[i]) - tam) <= max(8, tam * 0.15):
                    return (bordas[i] + bordas[j]) / 2.0, bordas[j] - bordas[i]
    e = bordas[0]
    if e + tam > hi:          # a borda final ficaria fora do mapa: e e a borda inicial
        return e + tam / 2.0, None
    if e - tam < lo:          # a borda inicial ficaria fora do mapa: e e a borda final
        return e - tam / 2.0, None
    return e + tam / 2.0, None


def acha_camera(raw, w, h, mapa, cam_w, cam_h):
    """Acha o retangulo branco (area visivel da camera) no minimapa, mesmo cortado pela borda do mapa.
    Devolve (cx, cy, tam_medido) em pixels da imagem; tam_medido = (largura, altura) se as 4 bordas
    apareceram, senao None. Devolve None se nao achar. So olha a moldura da propria camera."""
    if not raw or len(raw) < w * h * 4:
        return None
    b, g, r = (int.from_bytes(raw[i::4], "big") for i in (0, 1, 2))
    e = (b & g & r).to_bytes(w * h, "big")
    mask = e.translate(_TAB_BRANCO)
    linhas, colunas = [], []
    for y in range(h):
        if re.search(b"\x01{24,}", mask[y * w:(y + 1) * w]):
            linhas.append(y)
    for x in range(w):
        if re.search(b"\x01{16,}", mask[x::w]):
            colunas.append(x)
    cy, hm = _eixo(_grupos(linhas), cam_h, mapa[1], mapa[3])
    cx, wm = _eixo(_grupos(colunas), cam_w, mapa[0], mapa[2])
    if cx is None or cy is None:
        return None
    return cx, cy, ((wm, hm) if (wm and hm) else None)


def mouse_btn(nome, baixo):
    flag = {("esq", True): 0x2, ("esq", False): 0x4, ("dir", True): 0x8, ("dir", False): 0x10}[(nome, baixo)]
    user32.mouse_event(flag, 0, 0, 0, 0)


def cursor():
    p = wt.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def mover(x, y):
    user32.SetCursorPos(int(x), int(y))


def primeiro_plano():
    h = user32.GetForegroundWindow()
    if not h:
        return None
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    ph = kernel32.OpenProcess(0x1000, False, pid.value)
    if not ph:
        return None
    buf = ctypes.create_unicode_buffer(520)
    tam = wt.DWORD(520)
    ok = kernel32.QueryFullProcessImageNameW(ph, 0, buf, ctypes.byref(tam))
    kernel32.CloseHandle(ph)
    if not ok:
        return None
    r = wt.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    return os.path.basename(buf.value).lower(), (r.left, r.top, r.right, r.bottom)


def bipe(freq, ms):
    threading.Thread(target=lambda: kernel32.Beep(freq, ms), daemon=True).start()


# --------------------------------- DualSense -----------------------------------
def ler_estado(r):
    """Converte um relatorio HID do DualSense (BT 0x31 ou USB 0x01) em dict. None se nao reconhecer."""
    if len(r) >= 42 and r[0] == 0x31:
        s = r[2:]
    elif len(r) >= 64 and r[0] == 0x01:
        s = r[1:]
    else:
        return None
    b0, b1, b2 = s[7], s[8], s[9]
    hat = b0 & 0x0F
    cima = hat in (7, 0, 1)
    dir_ = hat in (1, 2, 3)
    baixo = hat in (3, 4, 5)
    esq = hat in (5, 6, 7)
    p = s[32:36]
    toca = not (p[0] & 0x80)
    tx = p[1] | ((p[2] & 0x0F) << 8)
    ty = (p[3] << 4) | (p[2] >> 4)
    return {
        "lx": (s[0] - 128) / 127.0, "ly": (s[1] - 128) / 127.0,
        "rx": (s[2] - 128) / 127.0, "ry": (s[3] - 128) / 127.0,
        "square": bool(b0 & 0x10), "cross": bool(b0 & 0x20), "circle": bool(b0 & 0x40), "triangle": bool(b0 & 0x80),
        "l1": bool(b1 & 0x01), "r1": bool(b1 & 0x02), "l2": bool(b1 & 0x04), "r2": bool(b1 & 0x08),
        "create": bool(b1 & 0x10), "options": bool(b1 & 0x20), "l3": bool(b1 & 0x40), "r3": bool(b1 & 0x80),
        "ps": bool(b2 & 0x01), "tpclick": bool(b2 & 0x02),
        "up": cima, "right": dir_, "down": baixo, "left": esq,
        "touch": toca, "tx": tx, "ty": ty,
        # giroscopio (bruto, ~16.4 por grau/s): pitch = inclinar frente/tras, yaw = girar para os lados
        "gpitch": struct.unpack_from("<h", bytes(s[15:17]))[0],
        "gyaw": struct.unpack_from("<h", bytes(s[17:19]))[0],
        "groll": struct.unpack_from("<h", bytes(s[19:21]))[0],
    }


class DualSense:
    def __init__(self):
        self.dev = None
        self.seq = 0

    def abrir(self):
        devs = [d for d in hid.enumerate(0x054C) if d["product_id"] in (0x0CE6, 0x0DF2)]
        if not devs:
            return False
        dev = hid.device()
        dev.open_path(devs[0]["path"])
        try:
            dev.get_feature_report(0x05, 41)      # liga o modo completo (touchpad, giroscopio...)
        except Exception as e:
            log.warning("feature 0x05 falhou: %s", e)
        dev.set_nonblocking(False)
        self.dev = dev
        log.info("DualSense aberto")
        self.saida(setup_luz=True)
        return True

    def fechar(self):
        try:
            if self.dev:
                self.dev.close()
        finally:
            self.dev = None

    def ler(self, timeout_ms=20):
        return self.dev.read(128, timeout_ms)

    def saida(self, cor=None, motor_esq=0, motor_dir=0, setup_luz=False, leds=None):
        """Relatorio de saida BT 0x31: luz (RGB), LEDs de jogador e vibracao. Ignora erros de escrita."""
        if not self.dev:
            return
        b = bytearray(78)
        b[0] = 0x31
        b[1] = (self.seq & 0x0F) << 4
        self.seq += 1
        b[2] = 0x10
        b[3] = 0x03                              # valid_flag0: vibracao (compat + haptica)
        b[4] = (0x04 if cor else 0x00) | (0x10 if leds is not None else 0x00)  # luz / LEDs de jogador
        b[5], b[6] = motor_dir & 0xFF, motor_esq & 0xFF
        b[41] = 0x02 | 0x04                      # valid_flag2: setup da luz + vibracao compat 2
        if setup_luz:
            b[44] = 0x02                         # lightbar_setup: desliga a pulsacao azul padrao
        if leds is not None:
            b[46] = leds & 0x1F
        if cor:
            b[47], b[48], b[49] = cor
        crc = zlib.crc32(b"\xA2" + bytes(b[:74])) & 0xFFFFFFFF
        b[74:78] = struct.pack("<I", crc)
        try:
            self.dev.write(bytes(b))
        except Exception as e:
            log.warning("escrita falhou: %s", e)


# ------------------------- dados do jogo (API oficial, so leitura) --------------
class Dados(threading.Thread):
    """Consulta a Live Client Data API (localhost:2999) e gera eventos de vibracao.
    Nao le memoria nem tela: so os numeros que a Riot publica para overlays."""

    def __init__(self):
        super().__init__(daemon=True)
        self.ctx = ssl._create_unverified_context()
        self.snap = None            # dict ou None (jogo fora do ar)
        self.eventos = []           # (nome, forca, ms)
        self.lock = threading.Lock()

    def get(self, caminho):
        url = "https://127.0.0.1:2999/liveclientdata/" + caminho
        with urllib.request.urlopen(url, context=self.ctx, timeout=1.0) as r:
            return json.loads(r.read())

    def emite(self, nome, forca, ms):
        with self.lock:
            self.eventos.append((nome, forca, ms))

    def pega_eventos(self):
        with self.lock:
            ev, self.eventos = self.eventos, []
        return ev

    def run(self):
        hp_ant = None
        pontos_ant = None
        morto_ant = None
        n = 0
        while True:
            try:
                ap = self.get("activeplayer")
                cs = ap["championStats"]
                hp, hpmax = float(cs["currentHealth"]), max(1.0, float(cs["maxHealth"]))
                niveis = sum(int(v.get("abilityLevel") or 0) for k, v in ap["abilities"].items() if k in "QWER")
                pontos = max(0, int(ap["level"]) - niveis)
                morto = morto_ant or False
                if n % 4 == 0:
                    nome = ap.get("riotIdGameName") or ap.get("summonerName")
                    for p in self.get("playerlist"):
                        if (p.get("riotIdGameName") or p.get("summonerName")) == nome:
                            morto = bool(p.get("isDead"))
                n += 1
                self.snap = {"hp": hp, "hpmax": hpmax, "pontos": pontos, "morto": morto}
                if hp_ant is not None and not morto and not (morto_ant or False):
                    perda = (hp_ant - hp) / hpmax
                    if VIBRA_DANO and perda >= DANO_MIN:
                        self.emite("dano", int(min(255, 90 + perda * 700)), 90)
                if VIBRA_EVENTOS:
                    if morto_ant is not None and morto and not morto_ant:
                        self.emite("morte", 255, 600)
                    if morto_ant and not morto:
                        self.emite("respawn", 160, 120)
                    if pontos_ant is not None and pontos > pontos_ant:
                        self.emite("ponto", 140, 70)
                hp_ant, pontos_ant, morto_ant = hp, pontos, morto
                time.sleep(0.2)
            except Exception:
                self.snap = None
                hp_ant = pontos_ant = morto_ant = None
                time.sleep(1.0)


# ----------------------------------- Motor -------------------------------------
BOTOES = ["square", "cross", "circle", "triangle", "l1", "r1", "l2", "r2", "create", "options",
          "l3", "r3", "tpclick", "up", "right", "down", "left"]

def P(tecla_, *mods):
    """Atalho padrao (reserva) = (modificadores, tecla), usado se o input.ini do jogo nao tiver o evento."""
    return (frozenset(mods), tecla_)


# botao do controle -> (evento no input.ini do jogo, atalho reserva). O DONO das teclas e o jogo:
# o que voce salvar em Opcoes > Teclas de atalho passa a valer aqui sozinho.
ACAO_BOTAO = {
    "l1": ("evtCastSpell1", P("q")), "l2": ("evtCastSpell2", P("w")),
    "r2": ("evtCastSpell3", P("e")), "cross": ("evtCastSpell4", P("r")),
    "square": ("evtCastAvatarSpell1", P("d")), "triangle": ("evtCastAvatarSpell2", P("f")),
    "circle": ("evtPlayerAttackMove", P("a")),
}
NIVEL_BOTAO = {          # Create + botao = subir habilidade (no jogo: evtLevelSpellN, normalmente Ctrl+tecla)
    "l1": ("evtLevelSpell1", P("q", "ctrl")), "l2": ("evtLevelSpell2", P("w", "ctrl")),
    "r2": ("evtLevelSpell3", P("e", "ctrl")), "cross": ("evtLevelSpell4", P("r", "ctrl")),
}
HABILIDADES = ("l1", "l2", "r2", "cross")       # segurar = mirar (stick direito + giroscopio)
BOTAO_AUTOATAQUE = "r1"  # clique esquerdo = atacar-mover no cursor (EnableLeftMouseButtonAttackMove do jogo)
ACAO_DPAD = {
    "left": ("evtUseItem1", P("1")), "right": ("evtUseItem2", P("2")),
    "up": ("evtUseVisionItem", P("4")),      # trinket / colocar ward
    "down": ("evtUseItem7", P("b")),         # voltar a base (recall)
}
ACAO_LOJA = ("evtOpenShop", P("p"))
ACAO_CAMERA = ("evtCameraLockToggle", P("y"))
ACAO_SO_CAMPEOES = ("evtChampionOnly", P("tab"))   # no jogo: TargetChampionsOnlyAsToggle=1 (liga/desliga)
MOD_ORDEM = ("ctrl", "alt", "shift")


def limita(v, a, b):
    return max(a, min(b, v))


class Atalhos:
    """Le o input.ini do LoL (atalhos do jogo) e recarrega sozinho quando o arquivo muda (ao salvar no jogo)."""

    def __init__(self, caminho):
        self.caminho = caminho
        self.cfg = os.path.join(os.path.dirname(caminho), "game.cfg")
        self.mtime = 0.0            # "versao" dos arquivos (muda quando input.ini ou game.cfg mudam)
        self._mt = (0.0, 0.0)
        self.mapa = {}              # eventos do input.ini (evtCastSpell1 -> "[q]")
        self.wasd = {}              # sobreposicoes do preset WASD (CastSpell1 -> "[1]")
        self.wasd_ativo = False     # game.cfg: WASD=1 (preset Keyboard (WASD) ligado no jogo)
        self.t_check = 0.0
        self.recarrega(forcar=True)

    def recarrega(self, forcar=False):
        agora = time.perf_counter()
        if not forcar and agora - self.t_check < 2.0:
            return
        self.t_check = agora
        try:
            mt = os.path.getmtime(self.caminho)
        except OSError:
            return
        try:
            mt2 = os.path.getmtime(self.cfg)
        except OSError:
            mt2 = 0.0
        if (mt, mt2) == self._mt:
            return
        mapa, wasd, secao = {}, {}, ""
        try:
            with open(self.caminho, encoding="utf-8", errors="ignore") as f:
                for linha in f:
                    linha = linha.strip()
                    if linha.startswith("["):
                        secao = linha.strip("[]").strip()
                    elif "=" in linha:
                        nome, valor = linha.split("=", 1)
                        (wasd if secao == "WASD" else mapa)[nome.strip()] = valor.strip()
        except OSError:
            return
        ativo = False
        try:
            with open(self.cfg, encoding="utf-8", errors="ignore") as f:
                for linha in f:
                    m = re.match(r"\s*WASD\s*=\s*(\d+)", linha)
                    if m:
                        ativo = m.group(1) == "1"
        except OSError:
            pass
        if PRESET == "wasd":
            ativo = True
        elif PRESET == "classico":
            ativo = False
        self.mapa, self.wasd, self.wasd_ativo = mapa, wasd, ativo
        self._mt, self.mtime = (mt, mt2), mt + mt2
        log.info("atalhos do jogo carregados (%d eventos; preset WASD %s)", len(mapa),
                 "LIGADO" if ativo else "desligado")

    def efetivo(self):
        """Eventos como o jogo os usa agora: input.ini + (se WASD=1) as sobreposicoes do preset WASD."""
        eff = dict(self.mapa)
        if self.wasd_ativo:
            for k, v in self.wasd.items():
                eff["evt" + k] = v
        return eff

    @staticmethod
    def parse(alt):
        toks = re.findall(r"\[([^\]]*)\]", alt)
        if not toks:
            return None
        mods, tecla_ = set(), None
        for t in toks:
            tl = t.strip().lower()
            if tl in MOD_ORDEM:
                mods.add(tl)
            elif tl in ("", "<unbound>") or tl.startswith("button"):
                return None
            else:
                tecla_ = tl
        if tecla_ and vk_de(tecla_) is not None:
            return (frozenset(mods), tecla_)
        return None

    def acao(self, evento, padrao):
        valor = self.wasd.get(evento[3:]) if (self.wasd_ativo and evento.startswith("evt")) else None
        valor = valor or self.mapa.get(evento)
        if valor:
            for alt in valor.split(","):
                r = self.parse(alt)
                if r:
                    return r
        return padrao


class Motor:
    def __init__(self, ds, dados=None):
        self.ds = ds
        self.dados = dados
        self.motor_forca = 0
        self.motor_ate = 0.0
        self.cor_ant, self.leds_ant, self.t_luz = None, None, 0.0
        self.pausado = False
        self.modo_mira = True
        self.mira_ativa = False
        self.soltou_em = 0.0
        self.ultima_acao = 0.0
        self.r3_t = 0.0
        self.t_diag = 0.0
        self.create_combo = False
        self.l3_combo = False
        self.autoataque_cursor = None
        self.so_campeoes = False
        self.giro_bias = None
        self.giro_off = [0.0, 0.0]
        self.giro_f = [0.0, 0.0]
        self.mirando_antes = False
        self.base_mira = None
        self.na_borda = False
        self.prev = {n: False for n in BOTOES}
        self.segurando = {}          # nome -> funcao que solta
        self.wasd = {k: False for k in ("w", "a", "s", "d", "up", "down", "left", "right")}
        self.teclas_stick = None
        self.stick_versao = None
        self.toque = False
        self.cursor_antes = None
        self.toque_origem = (0, 0)
        self.toque_cursor0 = (0, 0)
        self.toque_caixa = None      # limites do minimapa na tela durante o arrasto
        self.cam_wh = self.carregar_cam()
        self.acc = [0.0, 0.0]
        self.t_ant = time.perf_counter()
        self.fg = (0.0, None)
        self.centro = self.carregar_centro()
        self.at = Atalhos(INPUT_INI)
        self.atualiza_stick()

    # --- calibracao
    def carregar_centro(self):
        cp = configparser.ConfigParser()
        try:
            cp.read(ARQ_CALIB)
            return int(cp["centro"]["x"]), int(cp["centro"]["y"])
        except Exception:
            return None

    def calibrar(self, rect):
        x, y = cursor()
        self.centro = (x - rect[0], y - rect[1])
        cp = configparser.ConfigParser()
        cp["centro"] = {"x": str(self.centro[0]), "y": str(self.centro[1])}
        with open(ARQ_CALIB, "w") as f:
            cp.write(f)
        log.info("calibrado: %s", self.centro)
        bipe(1200, 110)
        bipe(1600, 150)
        self.pulso(200, 120)

    def carregar_cam(self):
        """Tamanho do retangulo da camera no minimapa (aprendido sozinho quando as 4 bordas aparecem)."""
        cp = configparser.ConfigParser()
        try:
            cp.read(ARQ_CALIB)
            return float(cp["camera"]["w"]), float(cp["camera"]["h"])
        except Exception:
            return 104.0, 56.0

    def salva_cam(self, wh):
        cp = configparser.ConfigParser()
        cp.read(ARQ_CALIB)
        cp["camera"] = {"w": "%.1f" % wh[0], "h": "%.1f" % wh[1]}
        with open(ARQ_CALIB, "w") as f:
            cp.write(f)

    def wasd_livre(self):
        """True se W, A, S e D estao livres para andar: no preset WASD eles SAO o movimento do jogo;
        no classico, so se nao estiverem ligados a nada (sem modificador)."""
        if self.at.wasd_ativo:
            return True
        for ev, val in self.at.efetivo().items():
            if not ev.startswith("evt") or "Smart" in ev or "SelfCast" in ev or "Normal" in ev:
                continue
            for alt in val.split(","):
                r = Atalhos.parse(alt)
                if r and not r[0] and r[1] in ("w", "a", "s", "d"):
                    log.info("WASD ocupado no jogo: '%s' = %s", r[1], ev)
                    return False
        return True

    def atualiza_stick(self):
        """Escolhe o que o stick esquerdo manda (WASD ou setas), de acordo com LEFT_STICK e com o jogo."""
        setas = {"up": "up", "down": "down", "left": "left", "right": "right"}
        wasd = {"up": "w", "down": "s", "left": "a", "right": "d"}
        if LEFT_STICK == "wasd":
            novo = wasd
        elif LEFT_STICK == "setas":
            novo = setas
        else:
            novo = wasd if self.wasd_livre() else setas
        if novo != self.teclas_stick:
            for k, v in self.wasd.items():          # solta o que estiver apertado do mapa antigo
                if v:
                    tecla(k, False)
                    self.wasd[k] = False
            self.teclas_stick = novo
            log.info("stick esquerdo -> %s", "WASD" if novo is wasd else "setas (camera)")
        self.stick_versao = self.at.mtime

    def centro_personagem(self, rect):
        if self.centro:
            return rect[0] + self.centro[0], rect[1] + self.centro[1]
        return (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2

    # --- luz / LEDs / vibracao
    def compor(self, agora):
        snap = self.dados.snap if self.dados else None
        if self.pausado:
            cor = COR_PAUSA
        elif not self.modo_mira:
            cor = COR_LIVRE
        elif LUZ_VIDA and snap:
            if snap["morto"]:
                cor = (50, 0, 0)
            else:
                r = limita(snap["hp"] / snap["hpmax"], 0.0, 1.0)
                cor = (int(255 * (1 - r) * 2), 255, 0) if r > 0.5 else (255, int(255 * r * 2), 0)
                if r < 0.25:
                    f = 0.3 + 0.7 * (math.sin(agora * 7) + 1) / 2
                    cor = tuple(int(c * f) for c in cor)
        else:
            cor = COR_MIRA
        leds = None
        if LEDS_PONTOS:
            n = min(5, snap["pontos"]) if snap else 0
            leds = (0x00, 0x04, 0x0A, 0x15, 0x1B, 0x1F)[n]
        return cor, leds

    def enviar(self, agora):
        cor, leds = self.compor(agora)
        f = self.motor_forca if agora < self.motor_ate else 0
        self.ds.saida(cor=cor, motor_esq=f, motor_dir=f, leds=leds)
        self.cor_ant, self.leds_ant, self.t_luz = cor, leds, agora

    def pulso(self, forca, ms):
        agora = time.perf_counter()
        self.motor_forca = forca
        self.motor_ate = agora + ms / 1000.0
        self.enviar(agora)

    def tarefas(self, agora):
        """Chamado a cada volta do laco: eventos de vibracao, fim de pulso e atualizacao da luz."""
        self.at.recarrega()
        if self.dados:
            for _nome, forca, ms in self.dados.pega_eventos():
                self.pulso(forca, ms)
        mudou = False
        if self.motor_forca and agora >= self.motor_ate:
            self.motor_forca = 0
            mudou = True
        if agora - self.t_luz >= 0.12:
            cor, leds = self.compor(agora)
            if cor != self.cor_ant or leds != self.leds_ant or agora - self.t_luz >= 1.0:
                mudou = True
        if mudou:
            self.enviar(agora)

    # --- soltar tudo
    def soltar_tudo(self):
        for f in list(self.segurando.values()):
            f()
        self.segurando.clear()
        for k in self.wasd:
            if self.wasd[k]:
                tecla(k, False)
                self.wasd[k] = False
        if self.toque:
            mouse_btn("esq", False)
            self.toque = False
        self.mira_ativa = False
        self.soltou_em = 0.0

    def foco(self):
        t = time.perf_counter()
        if t - self.fg[0] > 0.08:
            self.fg = (t, primeiro_plano())
        return self.fg[1]

    # --- acoes seguradas
    def segura_acao(self, nome, acao):
        """Aperta (modificadores + tecla) e segura ate soltar o botao. acao = (frozenset(mods), tecla)."""
        mods, k = acao
        ordem = [m for m in MOD_ORDEM if m in mods]
        for m in ordem:
            tecla(m, True)
        tecla(k, True)

        def soltar():
            tecla(k, False)
            for m in reversed(ordem):
                tecla(m, False)
        self.segurando[nome] = soltar

    def toca_acao(self, acao):
        mods, k = acao
        ordem = [m for m in MOD_ORDEM if m in mods]
        for m in ordem:
            tecla(m, True)
        tecla(k, True)
        tecla(k, False)
        for m in reversed(ordem):
            tecla(m, False)

    def segura_tecla(self, nome, k):
        self.segura_acao(nome, (frozenset(), k))

    def segura_mouse(self, nome, qual):
        mouse_btn(qual, True)
        self.segurando[nome] = lambda: mouse_btn(qual, False)

    def solta(self, nome):
        f = self.segurando.pop(nome, None)
        if f:
            f()

    def atualiza_giro(self, s, dt, mirando):
        """Aprende a deriva do giroscopio com o controle parado e, enquanto mira, soma o giro ao cursor."""
        g = (s["gpitch"], s["gyaw"])
        if self.giro_bias is None:
            self.giro_bias = [float(g[0]), float(g[1])]
        for i in (0, 1):
            dif = g[i] - self.giro_bias[i]
            if not mirando and abs(dif) < 80:     # parado (< ~5 graus/s): ajusta a deriva devagar
                self.giro_bias[i] += 0.002 * dif
        if not (GIRO_ATIVO and mirando):
            return
        # suaviza o tremor da mao (media movel exponencial) e converte para graus/s
        self.giro_f[0] += 0.3 * ((g[0] - self.giro_bias[0]) / 16.384 - self.giro_f[0])
        self.giro_f[1] += 0.3 * ((g[1] - self.giro_bias[1]) / 16.384 - self.giro_f[1])
        pitch, yaw = self.giro_f
        if abs(pitch) < GIRO_ZONA_GRAU_S:
            pitch = 0.0
        if abs(yaw) < GIRO_ZONA_GRAU_S:
            yaw = 0.0
        self.giro_off[0] += -yaw * dt * GIRO_PX_GRAU * (-1 if GIRO_INV_X else 1)
        self.giro_off[1] += -pitch * dt * GIRO_PX_GRAU * (-1 if GIRO_INV_Y else 1)

    def inicia_toque(self, rect, s):
        """Dedo encostou no touchpad: acha o retangulo da camera no minimapa e comeca o arrasto ali
        (assim o mapa nao pula; so se move conforme o dedo anda)."""
        W, H = rect[2] - rect[0], rect[3] - rect[1]
        x0, y0 = rect[0] + MINIMAPA[0] * W, rect[1] + MINIMAPA[1] * H
        x1, y1 = rect[0] + MINIMAPA[2] * W, rect[1] + MINIMAPA[3] * H
        self.toque_caixa = (x0, y0, x1, y1)
        margem = 10
        rx0, ry0 = int(x0) - margem, int(y0) - margem
        rw, rh = int(x1 - x0) + 2 * margem, int(y1 - y0) + 2 * margem
        partida = None
        try:
            raw = capturar(rx0, ry0, rw, rh)
            res = acha_camera(raw, rw, rh, (margem, margem, rw - margem, rh - margem), *self.cam_wh)
        except Exception:
            log.exception("falha ao achar a camera")
            res = None
        if res:
            cx, cy, wh = res
            partida = (rx0 + cx, ry0 + cy)
            if wh and 60 <= wh[0] <= 200 and 30 <= wh[1] <= 120 and \
                    (abs(wh[0] - self.cam_wh[0]) > 3 or abs(wh[1] - self.cam_wh[1]) > 3):
                self.cam_wh = wh
                self.salva_cam(wh)
                log.info("tamanho da camera no minimapa: %s", wh)
        if partida is None:       # nao achou: usa a posicao absoluta do dedo (como antes)
            u = limita((s["tx"] - TOUCH_X0) / float(TOUCH_X1 - TOUCH_X0), 0.0, 1.0)
            v = limita(s["ty"] / 1079.0, 0.0, 1.0)
            partida = (x0 + u * (x1 - x0), y0 + v * (y1 - y0))
        partida = (limita(partida[0], x0, x1), limita(partida[1], y0, y1))
        self.cursor_antes = cursor()
        self.toque_origem = (s["tx"], s["ty"])
        self.toque_cursor0 = partida
        mover(*partida)
        mouse_btn("esq", True)
        self.toque = True

    # --- processamento de um relatorio
    def processa(self, s):
        agora = time.perf_counter()
        dt = min(agora - self.t_ant, 0.05)
        self.t_ant = agora

        desc = {n: (s[n] and not self.prev[n]) for n in BOTOES}
        sobe = {n: ((not s[n]) and self.prev[n]) for n in BOTOES}
        self.prev = {n: s[n] for n in BOTOES}
        create = s["create"]
        if any(desc.values()):
            self.ultima_acao = agora      # apertou algo: o cursor nao volta ao personagem ainda

        # pausa: Create + Options (vale em qualquer janela)
        if desc["options"] and create:
            self.create_combo = True
            self.pausado = not self.pausado
            if self.pausado:
                self.soltar_tudo()
            bipe(500 if self.pausado else 900, 140)
            self.pulso(120, 100)
            return

        fg = self.foco()
        ativo = (not self.pausado) and fg is not None and fg[0] in ALVOS
        if (abs(s["rx"]) > 0.3 or abs(s["ry"]) > 0.3) and agora - self.t_diag > 1.0:
            self.t_diag = agora
            log.info("DIAG stick dir: ativo=%s foco=%s mira=%s toque=%s pausado=%s cursor=%s",
                     ativo, fg[0] if fg else None, self.modo_mira, self.toque, self.pausado, cursor())
        if not ativo:
            if self.segurando or self.toque or any(self.wasd.values()):
                self.soltar_tudo()
            return
        rect = fg[1]
        W, H = rect[2] - rect[0], rect[3] - rect[1]

        at = self.at
        # --- Create: segurado = modificador; so tocar = loja (tecla do jogo)
        if desc["create"]:
            self.create_combo = False
        if sobe["create"] and not self.create_combo:
            # no preset WASD a loja e P (testado no jogo); o input.ini so reflete o preset quando o jogo grava
            self.toca_acao(P("p") if at.wasd_ativo else at.acao(*ACAO_LOJA))

        # --- habilidades / feiticos / atacar-mover (com Create: subir habilidade)
        for n, (ev, pad) in ACAO_BOTAO.items():
            if n == "circle" and BOLA_SO_CAMPEOES:
                # Bola = liga/desliga "mirar so em campeoes" (funcao do proprio jogo, tecla evtChampionOnly)
                if desc[n]:
                    self.toca_acao(at.acao(*ACAO_SO_CAMPEOES))
                    self.so_campeoes = not self.so_campeoes
                    bipe(1100 if self.so_campeoes else 600, 90)
                    self.pulso(110 if self.so_campeoes else 60, 60)
                    log.info("so campeoes=%s", self.so_campeoes)
                continue
            if n == "circle" and at.wasd_ativo:
                # no preset WASD o 'A' e andar para a esquerda; atacar-mover ja e o clique esquerdo.
                # A Bola vira "centralizar camera" (segurar).
                ev, pad = "evtCameraSnap", P("space")
            if desc[n]:
                if s["l3"] and n in NIVEL_BOTAO:          # segurando L3 = subir habilidade
                    self.l3_combo = True
                    self.segura_acao(n, at.acao(*NIVEL_BOTAO[n]))
                else:
                    self.segura_acao(n, at.acao(ev, pad))
            elif sobe[n]:
                self.solta(n)
        # --- cliques
        # --- autoataque: atacar-mover (clique esquerdo). Com o stick direito solto, o clique sai nos pes do
        #     personagem, entao o PROPRIO JOGO ataca o inimigo mais perto de voce (com "so campeoes" ligado,
        #     o campeao mais perto). Com o stick direito apontando, ataca o mais perto de onde voce aponta.
        if desc[BOTAO_AUTOATAQUE]:
            self.autoataque_cursor = None
            mag_d = (s["rx"] ** 2 + s["ry"] ** 2) ** 0.5
            if AUTOATAQUE_MAIS_PERTO and mag_d <= ZONA_MORTA_MIRA:
                self.autoataque_cursor = cursor()
                mover(*self.centro_personagem(rect))
            elif self.modo_mira and mag_d > ZONA_MORTA_MIRA:
                # posiciona no ponto mirado ANTES do clique
                cx, cy = self.centro_personagem(rect)
                esc = MIRA_DISTANCIA if MIRA_POR_DIRECAO else min(1.0, (mag_d - ZONA_MORTA_MIRA) / (0.85 - ZONA_MORTA_MIRA))
                mover(round(cx + s["rx"] / mag_d * RAIO_X * esc), round(cy + s["ry"] / mag_d * RAIO_Y * esc))
            self.segura_mouse(BOTAO_AUTOATAQUE, "esq")
        elif sobe[BOTAO_AUTOATAQUE]:
            self.solta(BOTAO_AUTOATAQUE)
            if self.autoataque_cursor:
                mover(*self.autoataque_cursor)
                self.autoataque_cursor = None
        # --- L3: segurado = modificador de subir habilidade; toque sozinho = clique direito
        if desc["l3"]:
            self.l3_combo = False
        if sobe["l3"] and not self.l3_combo:
            mouse_btn("dir", True)
            mouse_btn("dir", False)
        # --- Options = Esc (sem Create)
        if desc["options"]:
            self.segura_tecla("options", "esc")
        elif sobe["options"]:
            self.solta("options")
        # --- direcional: itens / ward / voltar a base (teclas do jogo)
        for n, (ev, pad) in ACAO_DPAD.items():
            if desc[n]:
                self.segura_acao(n, at.acao(ev, pad))
            elif sobe[n]:
                self.solta(n)
        # --- clique do touchpad com Create = travar/destravar camera (tecla do jogo)
        if desc["tpclick"] and create:
            self.create_combo = True
            self.toca_acao(at.acao(*ACAO_CAMERA))
        # --- R3: toque curto alterna mira/livre; SEGURAR 1 s (ou Create + R3) calibra
        if desc["r3"]:
            if create:
                self.create_combo = True
                log.info("R3 com Create: calibrando")
                self.calibrar(rect)
                self.r3_t = -1.0
            else:
                self.r3_t = agora
        if self.r3_t > 0 and s["r3"] and agora - self.r3_t >= 1.0:
            log.info("R3 segurado: calibrando")
            self.calibrar(rect)
            self.r3_t = -1.0
        if sobe["r3"]:
            if self.r3_t > 0:               # soltou antes de 1 s: era um toque, alterna o modo
                self.modo_mira = not self.modo_mira
                self.mira_ativa = False
                self.soltou_em = 0.0
                bipe(900 if self.modo_mira else 500, 100)
                self.pulso(120, 70)
                log.info("modo mira=%s", self.modo_mira)
            self.r3_t = 0.0

        # --- stick esquerdo -> W A S D (ou setas)
        if self.at.mtime != self.stick_versao:
            self.atualiza_stick()
        ts = self.teclas_stick
        quer = {ts["up"]: s["ly"] < -ZONA_WASD, ts["down"]: s["ly"] > ZONA_WASD,
                ts["left"]: s["lx"] < -ZONA_WASD, ts["right"]: s["lx"] > ZONA_WASD}
        for k, v in quer.items():
            if v != self.wasd[k]:
                tecla(k, v)
                self.wasd[k] = v

        # --- touchpad: arrastar = clique esquerdo + movimento no minimapa, partindo de ONDE A CAMERA ESTA
        if s["touch"]:
            if not self.toque:
                self.inicia_toque(rect, s)
            else:
                x0, y0, x1, y1 = self.toque_caixa
                mover(limita(self.toque_cursor0[0] + (s["tx"] - self.toque_origem[0]) * TOUCH_GANHO, x0, x1),
                      limita(self.toque_cursor0[1] + (s["ty"] - self.toque_origem[1]) * TOUCH_GANHO, y0, y1))
        elif self.toque:
            mouse_btn("esq", False)
            self.toque = False
            if self.cursor_antes:
                mover(*self.cursor_antes)
            return

        if self.toque:
            return
        if self.autoataque_cursor and s[BOTAO_AUTOATAQUE]:
            return          # segurando o autoataque nos pes: nao mexe o cursor

        # --- stick direito (+ giroscopio enquanto segura habilidade/autoataque)
        rx, ry = s["rx"], s["ry"]
        mag = (rx * rx + ry * ry) ** 0.5
        mirando = MIRA_AO_SEGURAR and (any(s[n] for n in HABILIDADES) or s[BOTAO_AUTOATAQUE])
        if mirando and not self.mirando_antes:
            self.giro_off = [0.0, 0.0]
            self.base_mira = cursor()             # a mira parte de onde o cursor esta
        if not mirando:
            self.na_borda = False
        self.mirando_antes = mirando
        self.atualiza_giro(s, dt, mirando)
        if self.modo_mira or mirando:
            if mag > ZONA_MORTA_MIRA:
                cx, cy = self.centro_personagem(rect)
                if MIRA_POR_DIRECAO and not mirando:
                    esc = MIRA_DISTANCIA              # so a direcao importa: distancia fixa
                else:
                    esc = min(1.0, (mag - ZONA_MORTA_MIRA) / (0.85 - ZONA_MORTA_MIRA))
                self.base_mira = (cx + (rx / mag) * RAIO_X * esc, cy + (ry / mag) * RAIO_Y * esc)
                if mirando and VIBRA_BORDA:
                    borda = esc >= 1.0
                    if borda and not self.na_borda:
                        self.pulso(70, 30)        # chegou no limite do alcance
                    self.na_borda = borda
                if not mirando:
                    mover(round(self.base_mira[0]), round(self.base_mira[1]))
                self.mira_ativa = True
                self.soltou_em = 0.0
            else:
                if self.mira_ativa:
                    self.mira_ativa = False
                    self.soltou_em = agora
                # stick direito solto: mira no rumo em que o personagem anda (teclas W/A/S/D apertadas agora)
                if MIRA_SEGUE_MOVIMENTO and not mirando:
                    ts = self.teclas_stick
                    vx = int(self.wasd[ts["right"]]) - int(self.wasd[ts["left"]])
                    vy = int(self.wasd[ts["down"]]) - int(self.wasd[ts["up"]])
                    if vx or vy:
                        n = (vx * vx + vy * vy) ** 0.5
                        cx, cy = self.centro_personagem(rect)
                        self.base_mira = (cx + vx / n * RAIO_X * MIRA_DISTANCIA, cy + vy / n * RAIO_Y * MIRA_DISTANCIA)
                        mover(round(self.base_mira[0]), round(self.base_mira[1]))
                        self.soltou_em = 0.0
            if self.soltou_em and VOLTA_S > 0 and agora - max(self.soltou_em, self.ultima_acao) >= VOLTA_S:
                mover(*self.centro_personagem(rect))
                self.soltou_em = 0.0
            if mirando and self.base_mira:
                bx, by = self.base_mira
                mover(limita(round(bx + self.giro_off[0]), rect[0], rect[2] - 1),
                      limita(round(by + self.giro_off[1]), rect[1], rect[3] - 1))
        elif mag > ZONA_MORTA:
            esc = min(1.0, (mag - ZONA_MORTA) / (1 - ZONA_MORTA))
            fator = (esc ** 2) * VEL_LIVRE_PX_S * dt / mag
            self.acc[0] += rx * fator
            self.acc[1] += ry * fator
            dx, dy = round(self.acc[0]), round(self.acc[1])
            self.acc[0] -= dx
            self.acc[1] -= dy
            if dx or dy:
                x, y = cursor()
                mover(limita(x + dx, rect[0], rect[2] - 1), limita(y + dy, rect[1], rect[3] - 1))
        else:
            self.acc = [0.0, 0.0]


def instancia_unica():
    kernel32.CreateMutexW(None, False, "Global\\lol_controle_ps5")
    return ctypes.get_last_error() != 183


def principal():
    if not instancia_unica():
        log.info("ja existe uma instancia; saindo")
        return
    ds = DualSense()
    dados = Dados()
    dados.start()
    motor = Motor(ds, dados)
    log.info("iniciado")
    ultimo = 0.0
    bat = [0, 0.0, 0.0, 0.0, time.perf_counter()]      # batimento: contagem e maximos a cada 5 s
    while True:
        if not ds.dev:
            try:
                if not ds.abrir():
                    time.sleep(1.0)
                    continue
                motor.enviar(time.perf_counter())
            except Exception as e:
                log.warning("abrir falhou: %s", e)
                ds.fechar()
                time.sleep(1.0)
                continue
        try:
            r = ds.ler(20)
        except Exception as e:
            log.warning("leitura falhou: %s", e)
            motor.soltar_tudo()
            ds.fechar()
            continue
        try:
            motor.tarefas(time.perf_counter())
        except Exception:
            log.exception("erro nas tarefas de luz")
        if not r:
            if motor.segurando and time.perf_counter() - ultimo > 0.5:
                motor.soltar_tudo()      # controle sumiu: nao deixa tecla presa
            continue
        s = ler_estado(r)
        if s is None:
            continue
        ultimo = time.perf_counter()
        bat[0] += 1
        bat[1] = max(bat[1], abs(s["rx"]))
        bat[2] = max(bat[2], abs(s["ry"]))
        bat[3] = max(bat[3], abs(s["lx"]), abs(s["ly"]))
        if ultimo - bat[4] >= 5.0:
            fgi = motor.fg[1]
            log.info("VIVO relatorios=%d max_dir=(%.2f,%.2f) max_esq=%.2f foco=%s mira=%s toque=%s",
                     bat[0], bat[1], bat[2], bat[3], fgi[0] if fgi else None, motor.modo_mira, motor.toque)
            bat[:] = [0, 0.0, 0.0, 0.0, ultimo]
        try:
            motor.processa(s)
        except Exception:
            log.exception("erro no processamento")


# --------------------------------- utilitarios ---------------------------------
def modo_ver():
    """python lol_controle.py --ver  -> imprime o estado do controle por 20 s (diagnostico)."""
    ds = DualSense()
    if not ds.abrir():
        print("sem DualSense")
        return
    ant = None
    t0 = time.time()
    while time.time() - t0 < 20:
        r = ds.ler(50)
        s = ler_estado(r) if r else None
        if not s:
            continue
        res = [k for k, v in s.items() if v is True and k != "touch"]
        res += [f"{k}={round(s[k] * 2) / 2:+.1f}" for k in ("lx", "ly", "rx", "ry") if abs(s[k]) > 0.6]
        if s["touch"]:
            res.append(f"dedo=(x{s['tx'] // 480},y{s['ty'] // 360})")
        if res != ant:
            print(" ".join(res) if res else "(nada)", flush=True)
            ant = res
    ds.fechar()


def ajustar_jogo():
    """python lol_controle.py --ajustar-jogo  -> liga no game.cfg a opcao do LoL que limita o alvo do
    lancamento ao alcance maximo (stick no fim = habilidade no alcance maximo). So com o jogo FECHADO:
    aberto, ele regrava o arquivo ao sair. Guarda uma copia antes (game.cfg.bak-controle)."""
    import shutil
    import subprocess
    lista = subprocess.run(["tasklist", "/FI", "IMAGENAME eq League of Legends.exe"],
                           capture_output=True, text=True).stdout
    if "League of Legends.exe" in lista:
        print("Feche a partida primeiro (o jogo regrava o game.cfg ao sair).")
        return
    cfg = os.path.join(os.path.dirname(INPUT_INI), "game.cfg")
    with open(cfg, encoding="utf-8", errors="ignore") as f:
        texto = f.read()
    if not os.path.exists(cfg + ".bak-controle"):
        shutil.copy2(cfg, cfg + ".bak-controle")
    novo, n = re.subn(r"(?m)^ClampCastTargetLocationWithinMaxRange=\d+",
                      "ClampCastTargetLocationWithinMaxRange=1", texto)
    if n == 0:
        novo = re.sub(r"(?m)^\[General\]\s*$", "[General]\nClampCastTargetLocationWithinMaxRange=1", texto, count=1)
    with open(cfg, "w", encoding="utf-8") as f:
        f.write(novo)
    print("Pronto: ClampCastTargetLocationWithinMaxRange=1 (copia em game.cfg.bak-controle)")


def modo_luz():
    ds = DualSense()
    if not ds.abrir():
        print("sem DualSense")
        return
    for cor in (COR_MIRA, COR_LIVRE, COR_PAUSA, (255, 255, 255)):
        ds.saida(cor=cor)
        time.sleep(1.2)
    ds.saida(cor=COR_MIRA, motor_esq=220, motor_dir=220, leds=0x15)
    time.sleep(0.4)
    ds.saida(cor=COR_MIRA, leds=0x00)
    ds.fechar()


if __name__ == "__main__":
    if "--ver" in sys.argv:
        modo_ver()
    elif "--luz" in sys.argv:
        modo_luz()
    elif "--ajustar-jogo" in sys.argv:
        ajustar_jogo()
    else:
        principal()
