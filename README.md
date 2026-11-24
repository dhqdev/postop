# 🎬 PostOp

Plataforma para criar vídeos verticais (9:16) e postar no TikTok.

**Dois modos de geração**

1. **Cortes do YouTube**: cole um link. O PostOp baixa o vídeo, transcreve o áudio localmente (Whisper, grátis),
   a IA (OpenRouter) escolhe os melhores trechos e gera cortes 1080x1920 com legenda animada (palavra destacada),
   enquadramento automático no rosto ou fundo desfocado.
2. **Vídeo 3D por tema**: escolha um dos 14 temas prontos (Curiosidades, Terror, Mistérios, Lendas brasileiras,
   Mitologia, História em 1 minuto, Universo, Animais incríveis, E se...?, Ciência por dentro, Fábulas infantis,
   Motivação, Satisfatório, Humor absurdo) ou escreva uma ideia livre. Cada tema já traz ideias prontas, estilo visual,
   número de cenas e as regras do gênero para o roteirista. A IA escreve o roteiro em cenas, gera uma imagem 3D por cena
   (OpenRouter) e anima: **efeito 3D local** (movimento de câmera/parallax com ffmpeg, grátis) ou **IA de vídeo**
   do OpenRouter (image-to-video, pago por segundo). Junta as cenas com transições, texto na tela e música opcional.
   Os temas ficam em `app/pipelines/themes.py` (fácil de criar novos).

Depois é só postar no TikTok (Content Posting API oficial): publicação direta ou envio para os rascunhos do app.

## Stack

- **API + painel**: FastAPI (Python 3.12), painel em JS puro servido pela própria API.
- **Worker**: processa a fila guardada no Postgres (sem Redis), um job por vez.
- **Banco**: Postgres 16 próprio da stack.
- **Mídia**: ffmpeg, yt-dlp (+ Deno), faster-whisper, OpenCV (detecção de rosto).
- **IA**: OpenRouter (texto, imagem e vídeo). A API key é cadastrada na tela **Configurações** e fica criptografada.

## Modelos padrão (revisados em nov/2026)

| Uso | Modelo padrão | Custo aproximado |
|---|---|---|
| Escolher cortes / roteiro | `google/gemini-2.5-flash-lite` (reserva `openrouter/free`) | US$ 0,10 / 0,40 por milhão de tokens (centavos por vídeo); reserva grátis |
| Imagens 3D | `recraft/recraft-v4.1-flash-v2` (reserva `google/gemini-2.5-flash-image`) | ≈ US$ 0,007/imagem · reserva ≈ US$ 0,04/imagem |
| Vídeo por IA (opcional) | `google/veo-3.1-lite` | US$ 0,03/s sem áudio (cenas de 4, 6 ou 8 s) |
| Transcrição | Whisper local (`small`) | grátis |
| Animação 3D local | ffmpeg | grátis |

- A versão grátis do Recraft (`recraft/recraft-v4.1-flash-v2:free`) sai do OpenRouter em 28/11/2026. Quem já tinha
  salvo esse modelo passa a usar a versão paga automaticamente.
- Alternativas: `bytedance-seed/seedream-5-0-flash` (≈ US$ 0,018/imagem) e `bytedance/seedance-1-5-pro`
  (vídeo a partir de ≈ US$ 0,012/s).
- Sem créditos no OpenRouter, os modelos `:free` e o `openrouter/free` têm limite de 50 pedidos por dia
  (1.000 por dia depois de comprar US$ 10 em créditos).

Todos podem ser trocados em **Configurações → IA (OpenRouter)**, que mostra os recomendados e tem um botão para
listar os modelos e preços atuais.

## Deploy (Portainer / Docker Swarm)

1. Aponte o DNS do domínio (ex.: `postop.seudominio.com`) para o servidor.
2. Portainer → **Stacks → Add stack** → cole `deploy/postop-stack.yml` (usa o Traefik que já existe na rede
   `network_public`) ou `deploy/postop-stack-standalone.yml` (traz o próprio Traefik, para servidor sem proxy).
3. Troque os campos marcados com `<<< TROQUE` e clique em **Deploy the stack**.
4. Acesse o domínio, entre com `ADMIN_USER` / `ADMIN_PASSWORD`, cadastre a API key do OpenRouter e siga o
   **Passo a passo TikTok** dentro da plataforma.

Se o pacote da imagem no GHCR estiver privado, cadastre o registry `ghcr.io` no Portainer
(usuário do GitHub + token com `read:packages`) ou deixe o pacote público em GitHub → Packages → postop → Settings.

### Variáveis de ambiente

| Variável | Descrição |
|---|---|
| `ADMIN_USER`, `ADMIN_PASSWORD` | Login da plataforma |
| `PUBLIC_URL` | URL pública, sem barra no final (usada no Redirect URI do TikTok) |
| `SECRET_KEY` | Chave da sessão e da criptografia das configurações. Não troque depois de usar |
| `DATABASE_URL` | `postgresql://usuario:senha@host:5432/banco` |
| `DATA_DIR` | Pasta dos vídeos/modelos (padrão `/data`) |
| `API_WORKERS` | Processos do uvicorn (padrão 2) |

## CI/CD (GitHub Actions)

A cada push na `main`:

1. **Lint e testes** (ruff + pytest com ffmpeg real).
2. **Versão**: calcula a próxima versão semver pelos commits desde a última tag
   (`feat:` → minor, `!:`/`BREAKING CHANGE` → major, resto → patch).
3. **Imagem Docker** (amd64 e arm64, ex.: VPS Oracle Ampere) publicada em `ghcr.io/dhqdev/postop` com as tags `latest`, `X.Y.Z`, `X.Y` e `sha-…`.
4. **Release** `vX.Y.Z` criada no GitHub com as notas automáticas.

Para atualizar no Portainer: abra a stack e clique em **Update the stack** com **Re-pull image** ligado
(ou fixe uma versão, ex.: `ghcr.io/dhqdev/postop:0.2.0`).

## Desenvolvimento

```bash
docker compose up --build        # http://localhost:8000  (admin / admin)
# ou
pip install -r requirements-dev.txt
uvicorn app.main:app --reload    # API
python -m app.worker             # worker (outro terminal)
pytest -q && ruff check .
```
