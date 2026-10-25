from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", views.login_view, name="login"),
    path("sair/", views.logout_view, name="logout"),
    path("setup/", views.setup_view, name="setup"),
    path("saude/", views.saude, name="saude"),
    path("quiosque/", views.quiosque, name="quiosque"),
    path("api/reconhecer/", views.api_reconhecer, name="api_reconhecer"),
    path("pessoas/", views.pessoas, name="pessoas"),
    path("pessoas/nova/", views.pessoa_form, name="pessoa_nova"),
    path("pessoas/<int:pk>/editar/", views.pessoa_form, name="pessoa_editar"),
    path("pessoas/<int:pk>/alternar/", views.pessoa_alternar, name="pessoa_alternar"),
    path("pessoas/<int:pk>/excluir/", views.pessoa_excluir, name="pessoa_excluir"),
    path("registros/", views.registros, name="registros"),
    path("registros/manual/", views.registro_manual, name="registro_manual"),
    path("midia/<str:tipo>/<int:pk>/", views.midia, name="midia"),
    path("aws/", views.aws_config, name="aws"),
    path("usuarios/", views.usuarios, name="usuarios"),
    path("usuarios/novo/", views.usuario_novo, name="usuario_novo"),
    path("usuarios/<int:pk>/alternar/", views.usuario_alternar, name="usuario_alternar"),
    path("usuarios/<int:pk>/senha/", views.usuario_senha, name="usuario_senha"),
    path("auditoria/", views.auditoria, name="auditoria"),
]
