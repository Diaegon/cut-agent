---
name: cortes
description: Transforma uma palestra do YouTube em Shorts verticais (9:16) com legenda, escolhendo os trechos com maior potencial de viralizar. Use quando o usuário passar um link do YouTube e pedir cortes, shorts, reels, clipes ou trechos virais.
argument-hint: <url-do-youtube> [quantidade de cortes] [idioma]
---

# Cortes virais de palestras

Entrada: `$ARGUMENTS` (URL do YouTube; opcionalmente o número de cortes, padrão 5, e o idioma, ex.: `pt`).

Todos os comandos rodam a partir da raiz do projeto com `uv run`.

## 1. Baixar

```bash
uv run scripts/download.py "<url>"
```

A última linha impressa é o diretório de trabalho (`work/<id>`). Anote o título, o canal e a licença.
Se a licença não for Creative Commons, avise o usuário em uma linha que publicar cortes de terceiros
requer autorização do canal, e siga em frente.

## 2. Transcrever

```bash
uv run scripts/transcribe.py work/<id> --language <idioma> --model small
```

Use `--model medium` se o usuário pedir mais qualidade. Pode levar minutos em vídeos longos:
rode em background se passar de ~30 min de vídeo.

## 3. Escolher os cortes (este é o seu trabalho)

1. Leia `work/<id>/meta.json` (título e capítulos dão contexto) e `work/<id>/transcript.txt` inteiro.
   Se o arquivo for grande, leia em partes até cobrir tudo; não escolha olhando só o começo.
2. Aplique os critérios de [criteria.md](criteria.md). Primeiro liste mentalmente de 10 a 15 candidatos,
   depois fique só com os N melhores, sem sobreposição entre eles.
3. Para cada um, confira em `transcript.json` os timestamps exatos das palavras de início e de fim.
   O corte deve começar na primeira palavra do gancho, nunca em "então", "e aí" ou "como eu disse".
4. Escreva `work/<id>/clips.json`:

```json
[
  {
    "id": 1,
    "start": 734.2,
    "end": 781.9,
    "score": 8.7,
    "title": "Título curto que aparece no topo (máx. ~40 caracteres)",
    "hook": "a frase exata que abre o corte",
    "description": "1-2 frases para a descrição do Short, com crédito ao palestrante e link do vídeo original",
    "hashtags": ["#shorts", "#tema"],
    "reason": "por que esse trecho tem potencial (qual critério ele atende)"
  }
]
```

Ordene por `score` decrescente.

## 4. Renderizar

```bash
uv run scripts/render.py work/<id>
```

Opções: `--only <id>` re-renderiza um corte, `--no-title` remove o título do topo, `--no-captions`.

## 5. Revisar e entregar

- Para cada corte, extraia um frame do meio
  (`ffmpeg -v error -ss <t> -i work/<id>/out/clip_XX.mp4 -frames:v 1 /tmp/.../frame.jpg`) e olhe:
  o rosto está enquadrado? a legenda está legível? Se o enquadramento falhou (slide, plateia),
  diga isso ao usuário.
- Responda com uma tabela: arquivo, duração, score, título e gancho. Aponte para
  `work/<id>/out/posts.md`, que tem a descrição e as hashtags de cada corte.
- Se o usuário pedir ajustes ("começa 2s antes", "troca o título"), edite `clips.json` e rode
  `render.py --only <id>`.
