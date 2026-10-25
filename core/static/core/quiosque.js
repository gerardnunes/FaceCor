// Quiosque: captura quadros da webcam e envia ao servidor para reconhecimento
(() => {
  const root = document.getElementById("kiosk");
  if (!root) return;
  const video = document.getElementById("video");
  const cam = document.getElementById("cam");
  const res = document.getElementById("res");
  const tag = document.getElementById("tag");
  const nome = document.getElementById("nome");
  const sub = document.getElementById("sub");
  const relogio = document.getElementById("relogio");
  const url = root.dataset.url;
  const csrf = document.querySelector("meta[name=csrf]").content;
  const canvas = document.createElement("canvas");
  let ocupado = false;

  setInterval(() => {
    relogio.textContent = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }, 1000);

  function mostrar(estado, titulo, subtitulo, rotulo) {
    cam.className = "cam " + estado;
    res.className = "kres " + estado;
    tag.textContent = rotulo || "";
    nome.textContent = titulo;
    sub.textContent = subtitulo || "";
  }
  const ocioso = () => mostrar("", "Aproxime o rosto da câmera", "Olhe para a câmera para registrar entrada ou saída", "Aguardando");

  async function ciclo() {
    if (ocupado || video.readyState < 2) return;
    ocupado = true;
    let espera = 1200;
    try {
      const w = 640;
      canvas.width = w;
      canvas.height = Math.round((video.videoHeight / video.videoWidth) * w);
      canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise((r) => canvas.toBlob(r, "image/jpeg", 0.85));
      const fd = new FormData();
      fd.append("frame", blob, "frame.jpg");
      const r = await fetch(url, { method: "POST", body: fd, headers: { "X-CSRFToken": csrf }, credentials: "same-origin" });
      if (r.status === 403 || r.status === 401) { mostrar("bad", "Sessão expirada", "Entre novamente.", "Erro"); espera = 5000; }
      else {
        const d = await r.json();
        if (d.status === "ok") {
          const ent = d.tipo === "E";
          mostrar(ent ? "ok-in" : "ok-out", d.nome, d.setor || "", ent ? "ENTRADA registrada" : "SAÍDA registrada");
          espera = 4000;
        } else if (d.status === "cooldown") {
          mostrar(d.tipo === "E" ? "ok-in" : "ok-out", d.nome, "Registro já feito há instantes.", d.tipo === "E" ? "Entrada" : "Saída");
          espera = 3000;
        } else if (d.status === "desconhecido") {
          mostrar("bad", "Rosto não reconhecido", "Procure o responsável pelo COR.", "Acesso não identificado");
          espera = 3000;
        } else if (d.status === "sem_rosto") ocioso();
        else mostrar("bad", "Erro", d.msg || "", "Erro");
      }
    } catch (e) {
      mostrar("bad", "Sem conexão com o servidor", "Tentando novamente…", "Erro");
      espera = 3000;
    }
    setTimeout(() => { ocupado = false; if (espera > 1500) ocioso(); }, espera);
  }

  navigator.mediaDevices
    .getUserMedia({ video: { width: 1280, height: 720, facingMode: "user" }, audio: false })
    .then((s) => { video.srcObject = s; ocioso(); setInterval(ciclo, 700); })
    .catch(() => mostrar("bad", "Câmera indisponível", "Acesse por HTTPS e permita o uso da câmera.", "Erro"));
})();
