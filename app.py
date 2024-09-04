from flask import Flask, render_template, request, redirect, url_for, session, flash
import pandas as pd
import matplotlib.pyplot as plt
import io
import base64
from tabulate import tabulate
from datetime import datetime
import os
import functools

app = Flask(__name__)

# Defina uma chave secreta para gerenciar as sessões
# Em produção, use uma chave segura e mantenha-a em segredo (e.g., variável de ambiente)
app.secret_key = os.urandom(24)

# Usuários cadastrados (em um cenário real, você usaria um banco de dados)
users = {'julia.castro': 'bcard123'}

# Decorador para proteger rotas que requerem login
def login_required(f):
    @functools.wraps(f)
    def wrap(*args, **kwargs):
        if 'logged_in' in session:
            return f(*args, **kwargs)
        else:
            flash("Você precisa fazer login primeiro.")
            return redirect(url_for('login'))
    return wrap

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username in users and users[username] == password:
            session['logged_in'] = True
            session['username'] = username
            flash("Login bem-sucedido!")
            return redirect(url_for('index'))
        else:
            flash("Credenciais inválidas. Tente novamente.")
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('logged_in', None)
    session.pop('username', None)
    flash("Você foi desconectado.")
    return redirect(url_for('login'))

# Função para processar o arquivo Excel e gerar dados e gráficos para análise geral
def process_file(file):
    df_ativos = pd.read_excel(file, sheet_name='ATIVOS', parse_dates=['Data Admis.'])
    df_demitidos = pd.read_excel(file, sheet_name='DESLIGADOS', parse_dates=['Data Admis.', 'Dt. Demissao'])

    df_ativos['Data Admis.'] = pd.to_datetime(df_ativos['Data Admis.'], dayfirst=True)
    df_demitidos['Data Admis.'] = pd.to_datetime(df_demitidos['Data Admis.'], dayfirst=True)
    df_demitidos['Dt. Demissao'] = pd.to_datetime(df_demitidos['Dt. Demissao'], dayfirst=True)

    meses = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto']
    meses_num = [1, 2, 3, 4, 5, 6, 7, 8]

    demitidos_2024 = df_demitidos[df_demitidos['Dt. Demissao'].dt.year == 2024]
    demitidos_por_mes = demitidos_2024.groupby(demitidos_2024['Dt. Demissao'].dt.month).size().reindex(meses_num, fill_value=0).to_dict()

    ativos_por_mes = {}
    for mes_num, mes in zip(meses_num, meses):
        ativos_antes_mes = df_ativos[df_ativos['Data Admis.'] <= pd.Timestamp(f'2024-{mes_num:02d}-01')]
        demitidos_antes_mes = df_demitidos[(df_demitidos['Data Admis.'] <= pd.Timestamp(f'2024-{mes_num:02d}-01')) &
                                           (df_demitidos['Dt. Demissao'] > pd.Timestamp(f'2024-{mes_num:02d}-01'))]
        ativos_por_mes[mes] = len(ativos_antes_mes) + len(demitidos_antes_mes) - demitidos_por_mes[mes_num]

    demissoes_table = tabulate([['Mês', 'Quantidade de Demissões']] + [[mes.capitalize(), demitidos_por_mes[mes_num]] for mes_num, mes in zip(meses_num, meses)], tablefmt='html')
    ativos_table = tabulate([['Mês', 'Quantidade de Ativos']] + [[mes.capitalize(), count] for mes, count in ativos_por_mes.items()], tablefmt='html')

    graph_img = exibir_graficos(demitidos_por_mes, ativos_por_mes)

    return demissoes_table, ativos_table, graph_img

# Função para gerar e salvar gráficos para análise geral
def exibir_graficos(demitidos_por_mes, ativos_por_mes):
    meses = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto']
    meses_list = [mes.capitalize() for mes in meses]
    demissoes_valores = [demitidos_por_mes[i] for i in range(1, 9)]
    ativos_valores = [ativos_por_mes[mes] for mes in meses]

    plt.figure(figsize=(10, 5))

    plt.subplot(1, 2, 1)
    plt.bar(meses_list, demissoes_valores, color='salmon')
    plt.title('Quantidade de Demissões por Mês em 2024')
    plt.xlabel('Mês')
    plt.ylabel('Quantidade de Demissões')

    plt.subplot(1, 2, 2)
    plt.bar(meses_list, ativos_valores, color='skyblue')
    plt.title('Quantidade de Funcionários Ativos por Mês em 2024')
    plt.xlabel('Mês')
    plt.ylabel('Quantidade de Ativos')

    img = io.BytesIO()
    plt.tight_layout()
    plt.savefig(img, format='png')
    img.seek(0)
    graph_url = base64.b64encode(img.getvalue()).decode()
    plt.close()

    return f'data:image/png;base64,{graph_url}'

# Função para processar e analisar os dados de desligamento de um mês específico
def analyze_month(month, file):
    month_mapping = {
        'janeiro': ('DESLIGAMENTOS 01.24.xlsx', 'DESLIGUES JANEIRO 24'),
        'fevereiro': ('DESLIGAMENTOS 02.24.xlsx', 'DESLIGUES FEVEREIRO 24'),
        'marco': ('DESLIGAMENTOS 03.24.xlsx', 'DESLIGUES MARÇO'),
        'abril': ('DESLIGAMENTOS 04.24.xlsx', 'DESLIGUES ABRIL'),
        'maio': ('DESLIGAMENTOS 05.24.xlsx', 'DESLIGUES MAIO'),
        'junho': ('DESLIGAMENTOS 06.24.xlsx', 'DESLIGUES JUNHO'),
        'julho': ('DESLIGAMENTOS 07.24.xlsx', 'DESLIGUES JULHO'),
        'agosto': ('DESLIGAMENTOS 08.24.xlsx', 'DESLIGUES AGOSTO'),
        # Adicione os outros meses e seus arquivos
    }

    if month not in month_mapping:
        flash(f"Mês {month.capitalize()} não suportado.")
        return redirect(url_for('analyze'))

    caminho_planilha, aba = month_mapping[month]

    try:
        planilha = pd.read_excel(file, sheet_name=aba)

        if 'TIPO DE DESLIGAMENTO' not in planilha.columns:
            flash("'TIPO DE DESLIGAMENTO' não encontrado na aba do mês selecionado.")
            return redirect(url_for('analyze'))

        desligamentos_involuntarios = [
            'TERMINO DE CONTRATO POR PRAZO DETERMINADO - 2ª EXP.',
            'DISPENSA SEM JUSTA CAUSA',
            'TERMINO DE CONTRATO POR PRAZO DETERMINADO - 1ª EXP.',
            'TERMINO DE CONTRATO ANTECIPADO - EMPREGADOR',
            'DISPENSA POR JUSTA CAUSA'
        ]

        desligamentos_voluntarios = [
            'PEDIDO DE DESLIGAMENTO - SEM CUMPRIMENTO DE AVISO',
            'TERMINO DE CONTRATO ANTECIPADO - A PEDIDO DO EMPREGADO',
            'PEDIDO DE DESLIGAMENTO - COM CUMPRIMENTO DE AVISO'
        ]

        contagem_involuntarios = planilha[planilha['TIPO DE DESLIGAMENTO'].isin(desligamentos_involuntarios)].shape[0]
        contagem_voluntarios = planilha[planilha['TIPO DE DESLIGAMENTO'].isin(desligamentos_voluntarios)].shape[0]

        graph_img, bars_img = generate_graphs(contagem_involuntarios, contagem_voluntarios, planilha, desligamentos_involuntarios, desligamentos_voluntarios)

        return render_template('analyze_result.html', month=month.capitalize(), graph_img=graph_img, bars_img=bars_img)

    except FileNotFoundError:
        flash(f"Arquivo não encontrado: {caminho_planilha}")
        return redirect(url_for('analyze'))
    except KeyError as e:
        flash(f"Erro: {e}")
        return redirect(url_for('analyze'))

# Função para gerar gráficos para análise mensal
def generate_graphs(contagem_involuntarios, contagem_voluntarios, planilha, desligamentos_involuntarios, desligamentos_voluntarios):
    total_desligamentos = contagem_involuntarios + contagem_voluntarios
    percentuais = [
        contagem_involuntarios / total_desligamentos * 100 if total_desligamentos > 0 else 0,
        contagem_voluntarios / total_desligamentos * 100 if total_desligamentos > 0 else 0
    ]

    tipos_desligamento = ['Involuntárias', 'Voluntárias']
    valores = [contagem_involuntarios, contagem_voluntarios]
    plt.figure(figsize=(8, 6))
    plt.pie(valores, labels=tipos_desligamento, autopct='%1.1f%%', startangle=140, colors=['salmon', 'skyblue'])
    plt.title('Demissões por Tipo')
    plt.axis('equal')

    img = io.BytesIO()
    plt.savefig(img, format='png')
    img.seek(0)
    graph_url = base64.b64encode(img.getvalue()).decode()
    plt.close()

    tipos_especificos = desligamentos_involuntarios + desligamentos_voluntarios
    contagem_tipos_especificos = planilha['TIPO DE DESLIGAMENTO'].value_counts().reindex(tipos_especificos, fill_value=0)

    plt.figure(figsize=(10, 6))
    bars = plt.barh(tipos_especificos, contagem_tipos_especificos, color='lightcoral')
    plt.title('Tipos Específicos de Desligamento')
    plt.xlabel('Quantidade')
    plt.ylabel('Tipo de Desligamento')

    # Adicionar valores nas barras
    for bar in bars:
        width = bar.get_width()
        plt.text(width + 0.1, bar.get_y() + bar.get_height()/2, str(width), va='center')

    img2 = io.BytesIO()
    plt.tight_layout()
    plt.savefig(img2, format='png')
    img2.seek(0)
    bars_url = base64.b64encode(img2.getvalue()).decode()
    plt.close()

    return f'data:image/png;base64,{graph_url}', f'data:image/png;base64,{bars_url}'

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    return render_template('index.html')

@app.route('/general_analysis', methods=['GET', 'POST'])
@login_required
def general_analysis():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash("Nenhum arquivo enviado.")
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash("Nenhum arquivo selecionado.")
            return redirect(request.url)
        if file:
            demissoes_table, ativos_table, graph_img = process_file(file)
            return render_template('general_analysis.html', demissoes_table=demissoes_table, ativos_table=ativos_table, graph_img=graph_img)
    return render_template('general_analysis.html')

@app.route('/analyze', methods=['GET', 'POST'])
@login_required
def analyze():
    if request.method == 'POST':
        month = request.form.get('month')
        file = request.files.get('file')
        if not month:
            flash("Selecione um mês para análise.")
            return redirect(request.url)
        if not file or file.filename == '':
            flash("Nenhum arquivo enviado.")
            return redirect(request.url)
        return analyze_month(month, file)
    return render_template('analyze.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
