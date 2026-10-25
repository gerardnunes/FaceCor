# COR · Controle de Acesso (reconhecimento facial)

Sistema em Django para registrar **entradas e saídas** do Centro de Operações Remotas por reconhecimento facial, com fotos guardadas na **AWS S3** configurada pela própria interface (sem mexer em código). Tema escuro.

> **Status:** o código foi escrito sem poder ser executado no ambiente de desenvolvimento (sem acesso ao PyPI). Só a sintaxe Python foi verificada. Faça o primeiro deploy em um ambiente de teste e rode a checklist no final.

## Deploy (3 comandos)

Requisitos: um servidor com Docker + Docker Compose.

```bash
cp .env.example .env      # ajuste DOMAIN (e CADDY_GLOBAL, ver abaixo)
docker compose up -d --build
docker compose logs web   # mostra o TOKEN de configuração inicial
```

Abra `https://<DOMAIN>/setup/`, informe o token e crie o **login master**. Você será levado direto à tela **AWS S3**.

**HTTPS é obrigatório** (navegadores só liberam a câmera em HTTPS). O Caddy já está incluso:
- Rede interna / IP: `CADDY_GLOBAL=local_certs`. O navegador avisará do certificado; instale o certificado raiz do Caddy nos computadores do quiosque (`docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt .`).
- Domínio público: deixe `CADDY_GLOBAL=` vazio (Let's Encrypt automático, portas 80/443 abertas).

## Conectar a AWS S3 (pela interface)

Menu **AWS S3** (só o master): cole Access Key, Secret Key, região e bucket → **Testar conexão** (grava, lê e apaga um arquivo de teste) → **Salvar** (só ativa se o teste passar). A tela mostra a política IAM mínima. As chaves ficam **criptografadas** no banco; bucket privado, objetos com SSE-AES256. Enquanto a S3 não estiver ativa, as fotos ficam no disco do servidor (aviso no painel).

## Uso

- **Pessoas** (gestor/master): cadastre com a câmera ou arquivo. O sistema exige 1 rosto, e bloqueia rosto já cadastrado.
- **Quiosque**: abra `/quiosque/` num computador com webcam, logado como *Operador*. Alterna automaticamente Entrada/Saída por pessoa.
- **Registros**: filtros, foto de cada acesso, exportação CSV, lançamento manual (com motivo, auditado).
- **Auditoria** (master): logins, falhas, mudanças de AWS, cadastros, exportações.
- Papéis: **Master** (tudo), **Gestor** (pessoas/registros), **Operador** (só quiosque).

## Segurança incluída

- Setup inicial só com token; sem usuário padrão.
- Senhas ≥ 12 caracteres, bloqueio de 15 min após 5 falhas, sessão de 8 h, cookies seguros, HSTS, CSP restritiva, `X-Frame-Options: DENY`.
- Vetores faciais e credenciais AWS criptografados (Fernet/AES) com chave em `/data/field_key.txt` — **faça backup do volume `cor_data`**; sem essa chave os dados biométricos ficam ilegíveis.
- Fotos servidas apenas por rota autenticada (o bucket nunca fica público).
- Reconhecimento 100% local (OpenCV YuNet + SFace); nada é enviado a terceiros.
- Container roda sem root.

## Limitações conhecidas (leia)

- **Sem detecção de vivacidade (anti-spoofing):** uma foto/tela de celular de alta qualidade pode enganar o sistema. Para áreas críticas, combine com crachá/PIN ou câmera com infravermelho.
- Precisão depende de luz e posição da câmera; ajuste `FACE_THRESHOLD` (maior = mais rígido).
- **LGPD:** dado biométrico é sensível. Colete consentimento, defina prazo de retenção (a exclusão pelo master apaga a foto e o vetor) e restrinja o acesso ao servidor.
- SQLite basta para dezenas/centenas de pessoas; para mais volume, migre para PostgreSQL.

## Checklist do primeiro deploy

1. `docker compose up --build` conclui (baixa os modelos ONNX do GitHub no build).
2. `/setup/` cria o master; `/aws/` testa e salva a S3.
3. Cadastre uma pessoa com a câmera; veja a foto aparecer no bucket.
4. `/quiosque/`: primeira leitura = Entrada, segunda (após 15 s) = Saída.
5. Mostre um rosto não cadastrado → "não identificado" em Registros.

Sem Docker: `pip install -r requirements.txt`, baixe os dois `.onnx` (ver `Dockerfile`) para `models_onnx/`, rode `python manage.py makemigrations core && python manage.py migrate` e `gunicorn config.wsgi` atrás de um proxy HTTPS.
