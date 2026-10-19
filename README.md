---
tipo_registro: Sistema / Ativo construído
status: Ativo
updated_at: 2026-10-18
---

# LoL com controle PS5 (DualSense, Bluetooth)

Motor em Python que lê o DualSense direto (HID) e gera teclado + mouse, só com o LoL em foco.
**Ligar:** atalho "LoL com controle PS5" na Área de Trabalho (ou `.venv\Scripts\pythonw.exe lol_controle.py`).
**Parar:** atalho "Parar controle LoL" (`parar-controle.ps1`). **Pausar/retomar:** segurar Create + apertar Options.
Log: `lol_controle.log` (batimento a cada 5 s com o máximo dos sticks; `DIAG` quando o stick direito é usado).

## Mapa (preset "Keyboard (WASD)" do jogo)

| Controle | Faz |
|---|---|
| Stick esquerdo | W A S D (andar) |
| Stick direito | **Modo mira**: cursor = personagem + **direção** do stick, a distância fixa (`MIRA_DISTANCIA`); fica onde você mirou (precisa de câmera travada) |
| Stick direito solto | o cursor vai para a frente do personagem, **no rumo em que ele anda** (WASD) |
| R3 (toque) / R3 segurado 1 s | alterna MIRA ↔ LIVRE / **calibra** (mouse físico em cima do personagem) |
| R1 | autoataque: com o stick direito solto, atacar-mover nos pés (o **jogo** ataca o inimigo mais perto de você); com o stick apontando, o mais perto de onde aponta |
| Bola | liga/desliga **"mirar só em campeões"** do jogo (Tab). Bipe agudo = ligado, grave = desligado |
| L1 / L2 / R2 / X | habilidades 1 / 2 / 3 / 4 |
| L3 segurado + L1·L2·R2·X | subir habilidade 1 / 2 / 3 / 4 (Ctrl+Q/W/E/R) |
| *(desligado)* Segurando habilidade ou autoataque | stick direito mira, giroscópio ajusta fino, vibra no limite do alcance. Religar: `MIRA_AO_SEGURAR`, `GIRO_ATIVO`, `VIBRA_BORDA` |
| L3 (toque sozinho) | clique direito |
| Quadrado / Triângulo | feitiços 5 / 6 |
| Direcional | esq = item 7, dir = item 8, cima = 9 (ward), baixo = B (voltar à base) |
| Create (tocar) | loja (P) |
| Create + clique do touchpad | travar/destravar câmera |
| Touchpad (arrastar) | clique esquerdo no minimapa, partindo de onde a câmera está |
| Luz / LEDs / vibração | luz = vida (azul = cursor livre, roxo = pausa); LEDs = pontos de habilidade; vibra com dano, morte, ponto |

**Mira de habilidade estilo Wild Rift** (segurar = mirar, soltar = lançar): no jogo, em Opções → Teclas de atalho,
deixe as habilidades em **Quick Cast with Indicator** (lançamento rápido com indicador). **Alcance travado no máximo**:
com o jogo FECHADO, rode `python lol_controle.py --ajustar-jogo` (liga `ClampCastTargetLocationWithinMaxRange=1`
no `game.cfg`, com cópia de segurança). Ajustes do giroscópio no topo do script (`GIRO_*`).

As teclas vêm do próprio jogo: o motor lê `Config\input.ini` (o dono das teclas é o jogo). `PRESET = "wasd"` no topo
do script aplica as sobreposições do bloco `[WASD]`.

## Armadilhas (o que custou tempo)

- **Mouse injetado:** neste PC `MouseMove`/`mouse_event` relativo do AutoHotkey não movem o cursor; `SetCursorPos` move e
  `mouse_event` clica. O motor usa essas duas.
- **DualSense por Bluetooth:** o DirectInput do Windows só vê o modo simples. Abrir o controle com DS4Windows/Steam muda o
  modo e ele fica "mudo" para o Windows até desligar (segurar PS ~10 s) e religar. O motor pede o modo completo
  (relatório 0x31), que traz touchpad, giroscópio, luz e vibração.
- **Ctrl+1..4 são emotes** (risada etc.): subir nível é Ctrl+Q/W/E/R mesmo com habilidades nos números.
- **No preset WASD alguns atalhos vêm vazios**: Recall e subir habilidade 1/2. Configure no jogo
  (Opções → Teclas de atalho): Recall = B, subir habilidade 1 = Ctrl+Q, 2 = Ctrl+W, e clique Save.
- **Câmera semitravada** desloca o personagem na tela: travar com **C** (tecla do jogo, não Y) antes de calibrar.
- O jogo só grava o preset de teclas no arquivo mais tarde; por isso `PRESET` fixo no script.
- Não implementado de propósito: mira assistida (achar/escolher alvo lendo tela ou memória). A política de terceiros da
  Riot proíbe software que "toma ações em seu nome"; o risco é da conta. Só a API oficial `localhost:2999` (somente leitura) é usada.

## Instalação (Windows)

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pythonw.exe lol_controle.py
```

Requisitos: Windows 10/11, Python 3.10+, DualSense pareado por Bluetooth, LoL instalado em `C:\Riot Games`
(senão ajuste `INPUT_INI` no topo do script). Feche Steam e DS4Windows antes de usar (eles disputam o controle).
Diagnóstico: `python lol_controle.py --ver` mostra o que o controle envia; `--luz` testa luz e vibração.

## Arquivos

`lol_controle.py` (motor) · `calibracao.ini` (centro do personagem e tamanho da câmera no minimapa, gerado, fora do git) ·
`lol-controle-ps5.ahk` (versão antiga em AutoHotkey, reserva) · `parar-controle.ps1` (encerra o motor) ·
`requirements.txt` (`hidapi`).
