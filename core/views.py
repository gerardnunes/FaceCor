import csv
import logging
import secrets
import time
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import OuterRef, Subquery
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import face, storage
from .forms import AWSForm, LoginForm, PessoaForm, RegistroManualForm, SenhaForm, SetupForm, UsuarioForm
from .models import Auditoria, AWSConfig, Pessoa, Registro, User

log = logging.getLogger(__name__)
GERIR = (User.Papel.MASTER, User.Papel.GESTOR)
MASTER = (User.Papel.MASTER,)
MAX_FALHAS = 5
BLOQUEIO_MIN = 15


# ---------- utilidades ----------
def ip_cliente(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (xff.split(",")[0].strip() or request.META.get("REMOTE_ADDR")) or None


def auditar(request, acao, detalhe="", usuario=None):
    u = usuario or (request.user if request.user.is_authenticated else None)
    Auditoria.objects.create(
        usuario=u, usuario_texto=getattr(u, "username", ""), acao=acao, detalhe=detalhe[:300], ip=ip_cliente(request)
    )


def papel_requerido(*papeis):
    def deco(view):
        @wraps(view)
        def w(request, *a, **k):
            if request.user.papel not in papeis:
                raise PermissionDenied
            return view(request, *a, **k)

        return login_required(w)

    return deco


def csv_seguro(v):
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


# ---------- acesso ----------
def saude(request):
    return HttpResponse("ok")


def setup_view(request):
    if User.objects.exists():
        return redirect("login")
    form = SetupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        if not secrets.compare_digest(d["token"], settings.SETUP_TOKEN):
            form.add_error("token", "Token inválido.")
        else:
            u = User.objects.create_user(
                username=d["usuario"], email=d["email"], password=d["senha"], papel=User.Papel.MASTER, first_name="Master"
            )
            auditar(request, "setup", "Login master criado", usuario=u)
            login(request, u)
            messages.success(request, "Login master criado. Configure agora a conexão com a AWS S3.")
            return redirect("aws")
    return render(request, "core/setup.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        nome, senha = form.cleaned_data["usuario"], form.cleaned_data["senha"]
        u = User.objects.filter(username=nome).first()
        agora = timezone.now()
        if u and u.bloqueado_ate and u.bloqueado_ate > agora:
            auditar(request, "login_bloqueado", nome)
            messages.error(request, f"Conta bloqueada temporariamente. Tente novamente em {BLOQUEIO_MIN} minutos.")
        else:
            user = authenticate(request, username=nome, password=senha)
            if user and user.is_active:
                User.objects.filter(pk=user.pk).update(falhas=0, bloqueado_ate=None)
                login(request, user)
                auditar(request, "login", usuario=user)
                destino = request.GET.get("next", "")
                if url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                    return redirect(destino)
                return redirect("dashboard")
            time.sleep(0.6)
            if u:
                u.falhas += 1
                if u.falhas >= MAX_FALHAS:
                    u.falhas, u.bloqueado_ate = 0, agora + timedelta(minutes=BLOQUEIO_MIN)
                u.save(update_fields=["falhas", "bloqueado_ate"])
            auditar(request, "login_falhou", nome)
            messages.error(request, "Usuário ou senha incorretos.")
    return render(request, "core/login.html", {"form": form})


@require_POST
def logout_view(request):
    if request.user.is_authenticated:
        auditar(request, "logout")
    logout(request)
    return redirect("login")


# ---------- painel ----------
@login_required
def dashboard(request):
    if not request.user.pode_gerir:
        return redirect("quiosque")
    hoje = timezone.localdate()
    do_dia = Registro.objects.filter(momento__date=hoje)
    ultimo = Subquery(Registro.objects.filter(pessoa=OuterRef("pk")).order_by("-momento").values("tipo")[:1])
    dentro = Pessoa.objects.filter(ativo=True).annotate(ult=ultimo).filter(ult="E")
    ctx = {
        "entradas": do_dia.filter(tipo="E", desconhecido=False).count(),
        "saidas": do_dia.filter(tipo="S", desconhecido=False).count(),
        "desconhecidos": do_dia.filter(desconhecido=True).count(),
        "dentro_n": dentro.count(),
        "dentro": dentro[:30],
        "total_pessoas": Pessoa.objects.filter(ativo=True).count(),
        "recentes": Registro.objects.select_related("pessoa")[:10],
        "aws": AWSConfig.carregar(),
    }
    return render(request, "core/dashboard.html", ctx)


# ---------- quiosque / reconhecimento ----------
@login_required
def quiosque(request):
    return render(request, "core/quiosque.html")


@login_required
@require_POST
def api_reconhecer(request):
    arq = request.FILES.get("frame")
    if not arq or arq.size > 3 * 1024 * 1024:
        return JsonResponse({"status": "erro", "msg": "Imagem inválida."}, status=400)
    img = face.decodificar(arq.read())
    if img is None:
        return JsonResponse({"status": "erro", "msg": "Imagem inválida."}, status=400)
    res = face.extrair(img)
    if res is None:
        return JsonResponse({"status": "sem_rosto"})
    pid, sim = face.identificar(res.vetor)
    agora = timezone.now()

    def guardar_foto(prefixo):
        try:
            return storage.salvar(storage.nova_chave(prefixo), face.para_jpeg(img))
        except Exception:
            log.exception("Falha ao guardar foto do registro")  # nunca bloqueia a porta por falha de storage
            return ""

    if pid is None:
        if cache.add("cor_desconhecido", 1, 10):  # no máx. 1 alerta a cada 10 s
            Registro.objects.create(
                tipo="E", desconhecido=True, confianca=sim, foto_ref=guardar_foto("desconhecidos"), operador=request.user
            )
        return JsonResponse({"status": "desconhecido"})

    pessoa = Pessoa.objects.get(pk=pid)
    ult = Registro.objects.filter(pessoa=pessoa, desconhecido=False).order_by("-momento").first()
    if ult and (agora - ult.momento).total_seconds() < settings.FACE_COOLDOWN_SEG:
        return JsonResponse({"status": "cooldown", "nome": pessoa.nome, "tipo": ult.tipo})
    tipo = "S" if ult and ult.tipo == "E" else "E"
    Registro.objects.create(
        pessoa=pessoa, nome_snapshot=pessoa.nome, matricula_snapshot=pessoa.matricula, tipo=tipo,
        confianca=sim, foto_ref=guardar_foto(f"acessos/{timezone.localdate():%Y/%m/%d}"), operador=request.user,
    )
    return JsonResponse({"status": "ok", "nome": pessoa.nome, "setor": pessoa.setor, "tipo": tipo, "confianca": round(sim, 2)})


# ---------- pessoas ----------
@papel_requerido(*GERIR)
def pessoas(request):
    q = request.GET.get("q", "").strip()
    qs = Pessoa.objects.all()
    if q:
        qs = qs.filter(nome__icontains=q) | qs.filter(matricula__icontains=q)
    return render(request, "core/pessoas.html", {"pessoas": qs.order_by("nome"), "q": q})


@papel_requerido(*GERIR)
def pessoa_form(request, pk=None):
    pessoa = get_object_or_404(Pessoa, pk=pk) if pk else None
    form = PessoaForm(request.POST or None, request.FILES or None, instance=pessoa, foto_obrigatoria=pessoa is None)
    if request.method == "POST" and form.is_valid():
        p = form.save(commit=False)
        antiga = p.foto_ref
        try:
            if form.vetor is not None:
                p.definir_embedding(form.vetor)
                p.foto_ref = storage.salvar(storage.nova_chave("pessoas"), form.jpeg)
        except Exception:
            log.exception("Falha ao guardar foto")
            form.add_error(None, "Não foi possível guardar a foto (verifique a conexão com a AWS S3).")
        else:
            p.save()
            if form.vetor is not None and antiga:
                storage.apagar(antiga)
            auditar(request, "pessoa_editada" if pk else "pessoa_criada", f"{p.nome} ({p.matricula})")
            messages.success(request, "Pessoa salva.")
            return redirect("pessoas")
    return render(request, "core/pessoa_form.html", {"form": form, "pessoa": pessoa})


@papel_requerido(*GERIR)
@require_POST
def pessoa_alternar(request, pk):
    p = get_object_or_404(Pessoa, pk=pk)
    p.ativo = not p.ativo
    p.save()
    auditar(request, "pessoa_ativada" if p.ativo else "pessoa_desativada", p.nome)
    return redirect("pessoas")


@papel_requerido(*MASTER)
@require_POST
def pessoa_excluir(request, pk):
    p = get_object_or_404(Pessoa, pk=pk)
    storage.apagar(p.foto_ref)
    auditar(request, "pessoa_excluida", f"{p.nome} ({p.matricula})")
    p.delete()
    messages.success(request, "Pessoa e dados biométricos excluídos.")
    return redirect("pessoas")


# ---------- registros ----------
@papel_requerido(*GERIR)
def registros(request):
    qs = Registro.objects.select_related("pessoa")
    g = request.GET
    if g.get("de"):
        qs = qs.filter(momento__date__gte=g["de"])
    if g.get("ate"):
        qs = qs.filter(momento__date__lte=g["ate"])
    if g.get("tipo") in ("E", "S"):
        qs = qs.filter(tipo=g["tipo"])
    if g.get("q"):
        qs = qs.filter(nome_snapshot__icontains=g["q"]) | qs.filter(pessoa__nome__icontains=g["q"])
    if g.get("desconhecidos") == "1":
        qs = qs.filter(desconhecido=True)
    qs = qs.order_by("-momento")
    if g.get("export") == "csv":
        auditar(request, "export_csv", request.META.get("QUERY_STRING", ""))
        r = HttpResponse(content_type="text/csv; charset=utf-8")
        r["Content-Disposition"] = 'attachment; filename="registros-cor.csv"'
        r.write("﻿")
        w = csv.writer(r, delimiter=";")
        w.writerow(["Data/hora", "Matrícula", "Nome", "Tipo", "Método", "Confiança"])
        for x in qs[:50000]:
            w.writerow([
                timezone.localtime(x.momento).strftime("%d/%m/%Y %H:%M:%S"),
                csv_seguro(x.matricula_snapshot), csv_seguro(x.nome_exibicao), x.get_tipo_display(),
                x.get_metodo_display(), "" if x.confianca is None else f"{x.confianca:.2f}",
            ])
        return r
    page = Paginator(qs, 50).get_page(g.get("page"))
    params = g.copy()
    params.pop("page", None)
    return render(request, "core/registros.html", {
        "page": page, "g": g, "qs_base": params.urlencode(), "manual": RegistroManualForm(),
    })


@papel_requerido(*GERIR)
@require_POST
def registro_manual(request):
    form = RegistroManualForm(request.POST)
    if form.is_valid():
        d = form.cleaned_data
        p = d["pessoa"]
        Registro.objects.create(
            pessoa=p, nome_snapshot=p.nome, matricula_snapshot=p.matricula, tipo=d["tipo"],
            metodo="M", operador=request.user,
        )
        auditar(request, "registro_manual", f"{p.nome} {d['tipo']} — {d['motivo']}")
        messages.success(request, "Registro manual lançado.")
    else:
        messages.error(request, "Dados do registro manual inválidos.")
    return redirect("registros")


@papel_requerido(*GERIR)
def midia(request, tipo, pk):
    obj = get_object_or_404(Pessoa if tipo == "pessoa" else Registro, pk=pk) if tipo in ("pessoa", "registro") else None
    if obj is None or not obj.foto_ref:
        return HttpResponse(status=404)
    try:
        dados = storage.carregar(obj.foto_ref)
    except Exception:
        log.exception("Falha ao ler mídia")
        return HttpResponse(status=502)
    r = HttpResponse(dados, content_type="image/jpeg")
    r["Cache-Control"] = "private, no-store"
    return r


# ---------- AWS (login master) ----------
@papel_requerido(*MASTER)
def aws_config(request):
    cfg = AWSConfig.carregar()
    inicial = {"regiao": cfg.regiao, "bucket": cfg.bucket, "ativo": cfg.ativo, "access_key": cfg.chave_mascarada}
    form = AWSForm(request.POST or None, initial=inicial)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        ak = d["access_key"].strip()
        mascarada = bool(cfg.credenciais) and ak == cfg.chave_mascarada
        sk = d["secret_key"].strip()
        if (not ak or mascarada) and cfg.credenciais:
            ak = cfg.credenciais[0]
        if not sk and cfg.credenciais:
            sk = cfg.credenciais[1]
        if not ak or not sk:
            form.add_error(None, "Informe a Access Key e a Secret Key.")
        else:
            ok, msg = storage.testar_conexao(ak, sk, d["regiao"].strip(), d["bucket"], d["criar_bucket"])
            auditar(request, "aws_teste", f"{'OK' if ok else 'FALHA'} bucket={d['bucket']}")
            if "testar" in request.POST:
                (messages.success if ok else messages.error)(request, msg)
            elif ok or not d["ativo"]:
                cfg.definir_credenciais(ak, sk)
                cfg.regiao, cfg.bucket, cfg.ativo = d["regiao"].strip(), d["bucket"], d["ativo"] and ok
                cfg.save()
                auditar(request, "aws_salva", f"bucket={cfg.bucket} ativo={cfg.ativo}")
                messages.success(request, "Configuração salva. " + (msg if ok else "Credenciais salvas sem ativar (teste falhou)."))
                return redirect("aws")
            else:
                messages.error(request, f"Não salvo — o teste falhou: {msg}")
    return render(request, "core/aws.html", {"form": form, "cfg": cfg})


# ---------- usuários ----------
@papel_requerido(*MASTER)
def usuarios(request):
    return render(request, "core/usuarios.html", {"usuarios": User.objects.order_by("username")})


@papel_requerido(*MASTER)
def usuario_novo(request):
    form = UsuarioForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        u = form.save(commit=False)
        u.set_password(form.cleaned_data["senha"])
        u.save()
        auditar(request, "usuario_criado", f"{u.username} ({u.papel})")
        messages.success(request, "Usuário criado.")
        return redirect("usuarios")
    return render(request, "core/form.html", {"form": form, "titulo": "Novo usuário", "voltar": "usuarios"})


@papel_requerido(*MASTER)
@require_POST
def usuario_alternar(request, pk):
    u = get_object_or_404(User, pk=pk)
    if u.pk == request.user.pk:
        messages.error(request, "Você não pode desativar o próprio usuário.")
    else:
        u.is_active = not u.is_active
        u.save(update_fields=["is_active"])
        auditar(request, "usuario_ativado" if u.is_active else "usuario_desativado", u.username)
    return redirect("usuarios")


@papel_requerido(*MASTER)
def usuario_senha(request, pk):
    u = get_object_or_404(User, pk=pk)
    form = SenhaForm(request.POST or None, usuario=u)
    if request.method == "POST" and form.is_valid():
        u.set_password(form.cleaned_data["senha"])
        u.falhas, u.bloqueado_ate = 0, None
        u.save()
        auditar(request, "senha_redefinida", u.username)
        messages.success(request, "Senha redefinida.")
        return redirect("usuarios")
    return render(request, "core/form.html", {"form": form, "titulo": f"Redefinir senha — {u.username}", "voltar": "usuarios"})


@papel_requerido(*MASTER)
def auditoria(request):
    page = Paginator(Auditoria.objects.all(), 100).get_page(request.GET.get("page"))
    return render(request, "core/auditoria.html", {"page": page})
