#Requires AutoHotkey v2.0
#SingleInstance Force
; =====================================================================
;  League of Legends com controle PS5 (DualSense)
;  Le o controle e gera teclado + mouse. So atua com o LoL em foco.
;  Pausar/retomar: Ctrl+Alt+P   |   Sair: icone na bandeja > Exit
;
;  MAPA
;   (teclas do jogo no seu PC: habilidades 1 2 3 4, feiticos 5 6, itens 7 8 ...)
;   Stick direito ........ MODO MIRA: o cursor vai para (personagem + direcao do stick).
;                          Solta o stick = cursor volta ao personagem. Quanto mais empurra, mais longe.
;                          Precisa da CAMERA TRAVADA (tecla Y no jogo) + calibracao (Ctrl+Alt+C).
;   Touchpad (clique) .... alterna MIRA <-> LIVRE (LIVRE = cursor solto, para loja/minimapa/menus)
;   L1 / L2 / R1 / R2 .... habilidades 1 / 2 / 3 / 4  (Q W E R do seu jogo)
;   Quadrado / Triangulo . feiticos 5 / 6
;   Direcional ........... itens 7 (cima) 8 (direita) 9 (baixo) 0 (esquerda)  -> configure 9 e 0 no jogo
;   X .................... clique ESQUERDO (selecionar / confirmar)
;   L3 (clique stick esq). clique DIREITO (mover / atacar)
;   Bola ................. B (recall)
;   R3 (clique stick dir). A (atacar-mover; depois clique com X)
;   Stick esquerdo ....... W A S D
;   Options .............. Esc (menu)
;   Create (tocar) ....... P (loja)
;   Create (segurar) + L1/L2/R1/R2 = Ctrl+1/2/3/4 (subir habilidade)
;   CALIBRAR: trave a camera (Y), ponha o cursor (mouse fisico) em cima do seu personagem e
;             segure Create + aperte o touchpad (bipe duplo) -- ou Ctrl+Alt+C no teclado.
;   Touchpad sozinho: bipe agudo = MIRA, grave = LIVRE.
;  Cada aperto gera UMA acao (sem macros), como um teclado normal.
; =====================================================================

; ------------------------- AJUSTES (mexa aqui) -----------------------
VELOCIDADE_MOUSE := 24     ; pixels por ciclo com o stick no maximo (menor = mais lento)
ZONA_MORTA       := 0.18   ; ignora tremida do stick (0 a 1)
ZONA_CAMERA      := 0.40   ; quanto empurrar o stick esquerdo para virar W/A/S/D
INTERVALO_MS     := 8      ; ciclo de leitura
; --- modo mira
RAIO_X           := 600    ; alcance horizontal do cursor a partir do personagem (pixels)
RAIO_Y           := 380    ; alcance vertical (menor porque a camera e inclinada)
ZONA_MORTA_MIRA  := 0.25   ; stick precisa passar disso para mirar
VOLTA_MS         := 150    ; tempo apos soltar o stick para o cursor voltar ao personagem (0 = nunca volta)
; ---------------------------------------------------------------------

ProcessSetPriority "High"
SetKeyDelay -1, -1
CoordMode "Mouse", "Screen"

GroupAdd "LOL", "ahk_exe League of Legends.exe"
GroupAdd "LOL", "ahk_exe LeagueClientUx.exe"

; botao do controle -> tecla (numeros medidos neste controle)
TECLAS := Map(
    5, "1",       ; L1  -> habilidade 1
    7, "2",       ; L2  -> habilidade 2
    6, "3",       ; R1  -> habilidade 3
    8, "4",       ; R2  -> habilidade 4
    1, "5",       ; Quadrado -> feitico 1
    4, "6",       ; Triangulo -> feitico 2
    3, "b",       ; Bola -> recall
    12, "a",      ; R3 -> atacar-mover
    10, "Escape"  ; Options
)
FACE := Map(5, 1, 7, 1, 6, 1, 8, 1)   ; botoes que viram Ctrl+habilidade com Create segurado
BOTAO_CREATE := 9
BOTAO_CLIQUE_DIR := 11, BOTAO_CLIQUE_ESQ := 2    ; L3 = clique direito, X = clique esquerdo

estado := Map()        ; botao -> "string para soltar" enquanto apertado
dpadAtual := Map("up", 0, "right", 0, "down", 0, "left", 0)
camAtual  := Map("w", 0, "s", 0, "a", 0, "d", 0)   ; stick esquerdo = WASD
accX := 0.0, accY := 0.0
pausado := false
joy := 0
modoMira := true        ; true = mira (relativa ao personagem), false = livre
miraAtiva := false      ; stick direito esta mirando agora
soltouEm := 0           ; quando o stick foi solto (para o cursor voltar ao personagem)
createCombo := false    ; Create foi usado como modificador (entao nao vira P ao soltar)
createAntes := 0, toqueAntes := 0
ARQ_CALIB := A_ScriptDir "\calibracao.ini"
; posicao do personagem na tela, relativa ao canto da janela do jogo (0 = ainda nao calibrado)
centroX := Integer(IniRead(ARQ_CALIB, "centro", "x", 0))
centroY := Integer(IniRead(ARQ_CALIB, "centro", "y", 0))

CentroPersonagem(&cx, &cy) {
    global centroX, centroY
    WinGetPos(&wx, &wy, &ww, &wh, "A")
    if (centroX > 0 && centroY > 0) {
        cx := wx + centroX, cy := wy + centroY
    } else {
        cx := wx + ww // 2, cy := wy + wh // 2     ; padrao: meio da janela
    }
}

Calibrar() {
    global centroX, centroY, ARQ_CALIB
    MouseGetPos(&x, &y)
    WinGetPos(&wx, &wy, , , "A")
    centroX := x - wx, centroY := y - wy
    IniWrite(centroX, ARQ_CALIB, "centro", "x")
    IniWrite(centroY, ARQ_CALIB, "centro", "y")
    SoundBeep(1200, 120), SoundBeep(1600, 160)      ; bipe duplo = calibrado (tela do jogo pode esconder texto)
    ToolTip("Personagem calibrado em " centroX "," centroY)
    SetTimer(() => ToolTip(), -1800)
}

^!c:: {
    if WinActive("ahk_group LOL")
        Calibrar()
}

A_IconTip := "LoL + controle PS5"
^!p:: {
    global pausado
    pausado := !pausado
    if pausado
        SoltarTudo()
    ToolTip(pausado ? "Controle PS5: PAUSADO" : "Controle PS5: ATIVO")
    SetTimer(() => ToolTip(), -1500)
}

DetectarJoy() {
    Loop 16 {
        if (GetKeyState(A_Index "JoyName") != "")
            return A_Index
    }
    return 0
}

Soltar(rel) => (rel is Func) ? rel() : SendInput(rel)
Press(k)   => SendInput("{Blind}{" k " down}")
Release(k) => SendInput("{Blind}{" k " up}")

SoltarTudo() {
    global estado, dpadAtual, camAtual
    for b, rel in estado
        Soltar(rel)
    estado.Clear()
    for d, v in dpadAtual {
        if v
            SendInput("{Blind}{" DpadTecla(d) " up}")
        dpadAtual[d] := 0
    }
    for k, v in camAtual {
        if v
            SendInput("{Blind}{" k " up}")
        camAtual[k] := 0
    }
}

DpadTecla(d) {
    static m := Map("up", "7", "right", "8", "down", "9", "left", "0")
    return m[d]
}

Botao(b, apertado) {
    global estado, TECLAS, FACE, joy, BOTAO_CREATE, BOTAO_CLIQUE_DIR, BOTAO_CLIQUE_ESQ, createCombo
    if apertado {
        if estado.Has(b)
            return
        if (b = BOTAO_CLIQUE_ESQ) {
            ; clique via mouse_event (testado: o SendInput de mouse do AHK nao passa neste PC)
            DllCall("mouse_event", "UInt", 0x0002, "Int", 0, "Int", 0, "UInt", 0, "UPtr", 0)
            estado[b] := () => DllCall("mouse_event", "UInt", 0x0004, "Int", 0, "Int", 0, "UInt", 0, "UPtr", 0)
        } else if (b = BOTAO_CLIQUE_DIR) {
            DllCall("mouse_event", "UInt", 0x0008, "Int", 0, "Int", 0, "UInt", 0, "UPtr", 0)
            estado[b] := () => DllCall("mouse_event", "UInt", 0x0010, "Int", 0, "Int", 0, "UInt", 0, "UPtr", 0)
        } else if TECLAS.Has(b) {
            k := TECLAS[b]
            if (FACE.Has(b) && GetKeyState(joy "Joy" BOTAO_CREATE)) {
                createCombo := true
                SendInput("{Ctrl down}{" k " down}")
                estado[b] := "{" k " up}{Ctrl up}"
            } else {
                Press(k)
                estado[b] := "{Blind}{" k " up}"
            }
        }
    } else if estado.Has(b) {
        Soltar(estado[b])
        estado.Delete(b)
    }
}

Tick() {
    global joy, pausado, estado, dpadAtual, camAtual, accX, accY
    global VELOCIDADE_MOUSE, ZONA_MORTA, ZONA_CAMERA
    global RAIO_X, RAIO_Y, ZONA_MORTA_MIRA, VOLTA_MS
    global modoMira, miraAtiva, soltouEm, createCombo, createAntes, toqueAntes, BOTAO_CREATE
    if pausado || !WinActive("ahk_group LOL") {
        if (estado.Count || dpadAtual["up"] || dpadAtual["right"] || dpadAtual["down"] || dpadAtual["left"]
            || camAtual["w"] || camAtual["s"] || camAtual["a"] || camAtual["d"])
            SoltarTudo()
        return
    }
    if !joy {
        joy := DetectarJoy()
        if !joy
            return
    }
    ; --- botoes
    for b in [1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12]
        Botao(b, GetKeyState(joy "Joy" b))
    ; --- Create: segurado = modificador (Ctrl+habilidade); so tocar = P (loja)
    cr := GetKeyState(joy "Joy" BOTAO_CREATE) ? 1 : 0
    if (cr && !createAntes)
        createCombo := false
    if (!cr && createAntes && !createCombo)
        SendInput("{Blind}{p}")
    createAntes := cr
    ; --- touchpad: alterna MIRA <-> LIVRE
    tq := GetKeyState(joy "Joy14") ? 1 : 0
    if (tq && !toqueAntes) {
        if cr {
            ; Create segurado + touchpad = calibrar (cursor em cima do personagem, camera travada)
            createCombo := true
            Calibrar()
        } else {
            modoMira := !modoMira
            miraAtiva := false, soltouEm := 0
            SoundBeep(modoMira ? 900 : 500, 100)   ; agudo = mira, grave = livre
            ToolTip(modoMira ? "MODO MIRA" : "CURSOR LIVRE")
            SetTimer(() => ToolTip(), -1000)
        }
    }
    toqueAntes := tq
    ; --- direcional (itens)
    p := GetKeyState(joy "JoyPOV")
    quer := Map("up", 0, "right", 0, "down", 0, "left", 0)
    if (p >= 0) {
        if (p <= 4500 || p >= 31500)
            quer["up"] := 1
        if (p >= 4500 && p <= 13500)
            quer["right"] := 1
        if (p >= 13500 && p <= 22500)
            quer["down"] := 1
        if (p >= 22500 && p <= 31500)
            quer["left"] := 1
    }
    for d, v in quer {
        if (v != dpadAtual[d]) {
            SendInput("{Blind}{" DpadTecla(d) (v ? " down}" : " up}"))
            dpadAtual[d] := v
        }
    }
    ; --- stick esquerdo -> W A S D
    lx := (GetKeyState(joy "JoyX") - 50) / 50
    ly := (GetKeyState(joy "JoyY") - 50) / 50
    quer := Map("w", ly < -ZONA_CAMERA, "s", ly > ZONA_CAMERA, "a", lx < -ZONA_CAMERA, "d", lx > ZONA_CAMERA)
    for k, v in quer {
        v := v ? 1 : 0
        if (v != camAtual[k]) {
            SendInput("{Blind}{" k (v ? " down}" : " up}"))
            camAtual[k] := v
        }
    }
    ; --- stick direito
    rx := (GetKeyState(joy "JoyZ") - 50) / 50
    ry := (GetKeyState(joy "JoyR") - 50) / 50
    mag := Sqrt(rx * rx + ry * ry)
    if (modoMira) {
        ; MODO MIRA: cursor = personagem + direcao do stick (distancia proporcional ao quanto empurra)
        if (mag > ZONA_MORTA_MIRA) {
            CentroPersonagem(&cx, &cy)
            esc := Min(1.0, (mag - ZONA_MORTA_MIRA) / (0.85 - ZONA_MORTA_MIRA))
            ox := (rx / mag) * RAIO_X * esc
            oy := (ry / mag) * RAIO_Y * esc
            DllCall("SetCursorPos", "Int", Round(cx + ox), "Int", Round(cy + oy))
            miraAtiva := true, soltouEm := 0
        } else if (miraAtiva) {
            miraAtiva := false
            soltouEm := A_TickCount
        }
        if (soltouEm && VOLTA_MS > 0 && A_TickCount - soltouEm >= VOLTA_MS) {
            CentroPersonagem(&cx, &cy)
            DllCall("SetCursorPos", "Int", cx, "Int", cy)
            soltouEm := 0
        }
    } else if (mag > ZONA_MORTA) {
        ; MODO LIVRE: cursor solto, anda aos poucos como um mouse
        esc := Min(1.0, (mag - ZONA_MORTA) / (1 - ZONA_MORTA))
        fator := (esc ** 2) * VELOCIDADE_MOUSE / mag
        accX += rx * fator
        accY += ry * fator
        dx := Round(accX), dy := Round(accY)
        accX -= dx, accY -= dy
        if (dx || dy) {
            MouseGetPos(&x, &y)
            WinGetPos(&wx, &wy, &ww, &wh, "A")
            nx := Max(wx, Min(wx + ww - 1, x + dx))
            ny := Max(wy, Min(wy + wh - 1, y + dy))
            ; SetCursorPos: neste PC MouseMove/mouse_event nao movem o cursor (filtrados)
            DllCall("SetCursorPos", "Int", nx, "Int", ny)
        }
    } else {
        accX := 0.0, accY := 0.0
    }
}

OnExit((*) => SoltarTudo())
SetTimer(Tick, INTERVALO_MS)
