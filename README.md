# cut-agent — cortes virais de palestras com Claude Code

Uma *skill* do [Claude Code](https://claude.com/claude-code) que transforma uma palestra do YouTube em
**Shorts verticais (9:16) com legenda**, escolhendo os trechos com maior potencial de viralizar.

Você passa um link; o Claude baixa o vídeo, transcreve, lê a transcrição inteira, escolhe os melhores
trechos segundo critérios editoriais e renderiza cada corte com enquadramento no rosto do palestrante,
legenda palavra a palavra e título no topo.

```
/cortes https://www.youtube.com/watch?v=XXXXXXXXXXX 5 pt
```

## Como funciona

| Etapa | Quem faz | O quê |
|---|---|---|
| 1. Baixar | `scripts/download.py` | `yt-dlp` baixa até 1080p para `work/<id>/video.mp4` e salva `meta.json` (título, canal, licença, capítulos). |
| 2. Transcrever | `scripts/transcribe.py` | `faster-whisper` gera `transcript.json` (timestamps por palavra) e `transcript.txt` (versão compacta para o LLM ler). Usa GPU se disponível, senão CPU. |
| 3. Escolher | **Claude** | Lê a transcrição inteira, lista 10–15 candidatos, pontua com [`criteria.md`](.claude/skills/cortes/criteria.md) e escreve `clips.json`. |
| 4. Renderizar | `scripts/render.py` | Ajusta início/fim a limites de palavra, detecta o rosto (OpenCV) para um recorte 9:16 suavizado, gera legenda `.ass` com a palavra ativa destacada e codifica com `ffmpeg`. |
| 5. Revisar | **Claude** | Extrai um frame de cada corte, confere enquadramento e legenda, e entrega uma tabela + `posts.md` com descrição e hashtags. |

### Critérios de seleção

Cada candidato recebe nota de 0 a 10 em cinco eixos, com média ponderada:

- **Gancho** (peso 3) — os primeiros segundos prendem?
- **Autossuficiência** (peso 3) — quem não viu a palestra entende?
- **Payoff** (peso 2) — entrega o que o gancho promete?
- **Emoção / reação** (peso 1)
- **Citável / compartilhável** (peso 1)

Regras duras: 20–60 s, sem sobreposição, sem começar com conectivo, sem terminar no meio da frase,
sem depender de slide, sem distorcer o que o palestrante disse.

## Requisitos

- [Claude Code](https://docs.claude.com/en/docs/claude-code)
- [uv](https://docs.astral.sh/uv/) e Python 3.11 ou 3.12
- `ffmpeg` / `ffprobe` com `libass` (para queimar a legenda)
- Fonte **Montserrat** instalada (ou passe outra com `--font`)
- Opcional: GPU NVIDIA com CUDA 12 + cuBLAS/cuDNN para transcrição rápida

## Instalação

```bash
git clone https://github.com/Diaegon/cut-agent.git
cd cut-agent
uv sync
```

A skill fica em `.claude/skills/cortes/` e é carregada automaticamente quando você abre o
Claude Code na raiz do projeto.

## Uso

No Claude Code, dentro da pasta do projeto:

```
/cortes <url-do-youtube> [quantidade de cortes] [idioma]
```

Ou simplesmente peça: *"faz 5 cortes dessa palestra: https://youtu.be/..."*.

Depois peça ajustes em linguagem natural — *"o corte 3 começa 2 s antes"*, *"troca o título do 1"* — e
o Claude edita `clips.json` e re-renderiza só aquele corte.

### Rodando os scripts manualmente

```bash
uv run scripts/download.py "<url>"                        # imprime work/<id>
uv run scripts/transcribe.py work/<id> --language pt --model small   # --model medium p/ mais qualidade, --cpu p/ forçar CPU
# escreva work/<id>/clips.json (formato em .claude/skills/cortes/SKILL.md)
uv run scripts/render.py work/<id>                        # --only <id>, --no-title, --no-captions, --font "Nome"
```

### Saída

```
work/<id>/
├── video.mp4          # original (não versionado)
├── meta.json
├── transcript.json
├── transcript.txt
├── clips.json         # cortes escolhidos
└── out/
    ├── clip_01.mp4    # 1080x1920, H.264 + AAC
    ├── ...
    └── posts.md       # título, descrição e hashtags de cada corte
```

A pasta `work/` e todos os arquivos de vídeo estão no `.gitignore`.

## Estrutura do repositório

```
.claude/skills/cortes/
├── SKILL.md       # o passo a passo que o Claude segue
└── criteria.md    # critérios editoriais para escolher os cortes
scripts/
├── download.py
├── transcribe.py
└── render.py
pyproject.toml
```

## Limitações conhecidas / próximos passos

- **Planos abertos e trocas de câmera**: o recorte segue o rosto; em planos de palco ou de plateia o
  enquadramento pode ficar ruim. Ideia: detectar corte de cena e usar o quadro inteiro com fundo desfocado.
- **Detector de rosto**: usa Haar cascade (por isso `opencv<5`). Trocar por YuNet ou MediaPipe deve
  melhorar a precisão.
- **GPU**: se faltar `libcublas.so.12`, a transcrição cai para CPU. Instale `nvidia-cublas-cu12` no venv.

## Direitos autorais

Publicar cortes de vídeos de terceiros exige autorização do dono do conteúdo, a menos que o vídeo
tenha licença que permita reuso (ex.: Creative Commons). A skill avisa quando a licença não é CC,
e a descrição gerada inclui crédito ao palestrante e link para o original.
