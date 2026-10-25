// Câmera do cadastro de pessoas (captura uma foto e coloca no campo de arquivo do formulário)
(() => {
  const root = document.getElementById("enroll");
  if (!root) return;
  const video = root.querySelector("video");
  const preview = root.querySelector("img.snap");
  const canvas = document.createElement("canvas");
  const input = document.getElementById("id_foto");
  const btnStart = document.getElementById("cam-start");
  const btnSnap = document.getElementById("cam-snap");
  const aviso = document.getElementById("cam-aviso");
  let stream = null;

  btnStart.addEventListener("click", async () => {
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720, facingMode: "user" }, audio: false });
      video.srcObject = stream;
      video.classList.remove("hidden");
      preview.classList.add("hidden");
      btnSnap.classList.remove("hidden");
      aviso.textContent = "";
    } catch (err) {
      aviso.textContent = "Não foi possível acessar a câmera (é preciso HTTPS e permitir o acesso). Envie uma foto pelo arquivo.";
    }
  });

  btnSnap.addEventListener("click", () => {
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    canvas.toBlob((blob) => {
      const file = new File([blob], "captura.jpg", { type: "image/jpeg" });
      const dt = new DataTransfer();
      dt.items.add(file);
      input.files = dt.files;
      preview.src = URL.createObjectURL(blob);
      preview.classList.remove("hidden");
      video.classList.add("hidden");
      if (stream) stream.getTracks().forEach((t) => t.stop());
      btnSnap.classList.add("hidden");
    }, "image/jpeg", 0.92);
  });
})();
