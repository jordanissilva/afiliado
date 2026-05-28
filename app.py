import os
import psycopg2
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.utils import secure_filename
from functools import wraps

# ─── CONFIGURAÇÃO DE CAMINHOS ABSOLUTOS ──────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
STATIC_DIR = os.path.join(BASE_DIR, 'static')
UPLOAD_FOLDER = os.path.join(STATIC_DIR, 'uploads')

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
app.secret_key = 'chave-secreta-super-segura-2026'

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB

# ─── CREDENCIAIS DO ADMIN ───────────────────────────────────────────────────
ADMIN_EMAIL = 'admin@email.com'
ADMIN_PASSWORD = '123456'


# ─── Conexão Inteligente com o Banco de Dados ───────────────────────────────

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        database_url = os.environ.get('DATABASE_URL')
        if database_url:
            # Se estiver na internet (Render), conecta no PostgreSQL
            db = g._database = psycopg2.connect(database_url)
        else:
            # Se estiver no computador, conecta no SQLite local de forma adaptada
            import sqlite3
            sqlite_db = os.path.join(BASE_DIR, 'database.db')
            db = g._database = sqlite3.connect(sqlite_db)
            db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def init_db():
    with app.app_context():
        db = get_db()
        # Se for PostgreSQL (Render)
        if hasattr(db, 'cursor') and not hasattr(db, 'row_factory'):
            cur = db.cursor()
            cur.execute('''
                        CREATE TABLE IF NOT EXISTS produtos
                        (
                            id
                            SERIAL
                            PRIMARY
                            KEY,
                            nome
                            TEXT
                            NOT
                            NULL,
                            descricao
                            TEXT,
                            categoria
                            TEXT,
                            imagem
                            TEXT,
                            link
                            TEXT
                            NOT
                            NULL,
                            destaque
                            INTEGER
                            DEFAULT
                            0
                        )
                        ''')
            cur.execute('''
                        CREATE TABLE IF NOT EXISTS categorias
                        (
                            id
                            SERIAL
                            PRIMARY
                            KEY,
                            nome
                            TEXT
                            NOT
                            NULL
                            UNIQUE
                        )
                        ''')
            cur.execute('SELECT COUNT(*) FROM categorias')
            qtd = cur.fetchone()[0]
            if qtd == 0:
                categorias_padrao = ['Eletrônicos', 'Fitness', 'Acessórios', 'Casa', 'Mochilas', 'Tecnologia', 'Livros']
                for cat in categorias_padrao:
                    cur.execute('INSERT INTO categorias (nome) VALUES (%s)', (cat,))
            db.commit()
            cur.close()
        else:
            # Se for SQLite (Computador)
            db.execute('''
                       CREATE TABLE IF NOT EXISTS produtos
                       (
                           id
                           INTEGER
                           PRIMARY
                           KEY
                           AUTOINCREMENT,
                           nome
                           TEXT
                           NOT
                           NULL,
                           descricao
                           TEXT,
                           categoria
                           TEXT,
                           imagem
                           TEXT,
                           link
                           TEXT
                           NOT
                           NULL,
                           destaque
                           INTEGER
                           DEFAULT
                           0
                       )
                       ''')
            db.execute('''
                       CREATE TABLE IF NOT EXISTS categorias
                       (
                           id
                           INTEGER
                           PRIMARY
                           KEY
                           AUTOINCREMENT,
                           nome
                           TEXT
                           NOT
                           NULL
                           UNIQUE
                       )
                       ''')
            check = db.execute('SELECT COUNT(*) as qtd FROM categorias').fetchone()
            if check['qtd'] == 0:
                categorias_padrao = ['Eletrônicos', 'Fitness', 'Acessórios', 'Casa', 'Mochilas', 'Tecnologia', 'Livros']
                for cat in categorias_padrao:
                    db.execute('INSERT INTO categorias (nome) VALUES (?)', (cat,))
            db.commit()


def carregar_categorias():
    db = get_db()
    if hasattr(db, 'cursor') and not hasattr(db, 'row_factory'):
        cur = db.cursor()
        cur.execute('SELECT nome FROM categorias ORDER BY nome ASC')
        rows = cur.fetchall()
        cur.close()
        return [row[0] for row in rows]
    else:
        rows = db.execute('SELECT nome FROM categorias ORDER BY nome ASC').fetchall()
        return [row['nome'] for row in rows]


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ─── Controle de Acesso ───────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Faça login para acessar esta página.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated


# ─── Rota Principal ───────────────────────────────────────────────────────────

@app.route('/')
def index():
    db = get_db()
    categoria = request.args.get('categoria', '')
    busca = request.args.get('busca', '').strip()

    if hasattr(db, 'cursor') and not hasattr(db, 'row_factory'):  # PostgreSQL
        cur = db.cursor()
        cur.execute(
            'SELECT id, nome, descricao, categoria, imagem, link, destaque FROM produtos WHERE destaque = 1 ORDER BY id DESC')
        livros_cru = cur.fetchall()

        # Converte lista em dicionários para o HTML ler igual nos dois bancos
        livros_indicados = []
        for r in livros_cru:
            livros_indicados.append(
                {'id': r[0], 'nome': r[1], 'descricao': r[2], 'categoria': r[3], 'imagem': r[4], 'link': r[5],
                 'destaque': r[6]})

        query = 'SELECT id, nome, descricao, categoria, imagem, link, destaque FROM produtos WHERE 1=1'
        params = []
        if categoria:
            query += ' AND categoria = %s'
            params.append(categoria)
        if busca:
            query += ' AND (nome LIKE %s OR descricao LIKE %s)'
            params.extend([f'%{busca}%', f'%{busca}%'])
        query += ' ORDER BY id DESC'

        cur.execute(query, params)
        produtos_cru = cur.fetchall()
        cur.close()

        produtos = []
        for r in produtos_cru:
            produtos.append(
                {'id': r[0], 'nome': r[1], 'descricao': r[2], 'categoria': r[3], 'imagem': r[4], 'link': r[5],
                 'destaque': r[6]})
    else:  # SQLite
        livros_indicados = db.execute('SELECT * FROM produtos WHERE destaque = 1 ORDER BY id DESC').fetchall()
        query = 'SELECT * FROM produtos WHERE 1=1'
        params = []
        if categoria:
            query += ' AND categoria = ?'
            params.append(categoria)
        if busca:
            query += ' AND (nome LIKE ? OR descricao LIKE ?)'
            params.extend([f'%{busca}%', f'%{busca}%'])
        query += ' ORDER BY id DESC'
        produtos = db.execute(query, params).fetchall()

    return render_template('index.html',
                           produtos=produtos,
                           livros_indicados=livros_indicados,
                           categorias=carregar_categorias(),
                           categoria_atual=categoria,
                           busca=busca)


# ─── Painel Administrativo (CRUD) ─────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('admin'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        senha = request.form.get('senha', '')

        if email == ADMIN_EMAIL and senha == ADMIN_PASSWORD:
            session['logged_in'] = True
            session['admin_email'] = email
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('admin'))
        else:
            flash('E-mail ou senha incorretos.', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Você saiu da conta.', 'info')
    return redirect(url_for('login'))


@app.route('/admin')
@login_required
def admin():
    db = get_db()
    if hasattr(db, 'cursor') and not hasattr(db, 'row_factory'):
        cur = db.cursor()
        cur.execute('SELECT id, nome, descricao, categoria, imagem, link, destaque FROM produtos ORDER BY id DESC')
        produtos_cru = cur.fetchall()
        cur.close()
        produtos = []
        for r in produtos_cru:
            produtos.append(
                {'id': r[0], 'nome': r[1], 'descricao': r[2], 'categoria': r[3], 'imagem': r[4], 'link': r[5],
                 'destaque': r[6]})
    else:
        produtos = db.execute('SELECT * FROM produtos ORDER BY id DESC').fetchall()
    return render_template('admin.html', produtos=produtos)


@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_produto():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        descricao = request.form.get('descricao', '').strip()
        categoria = request.form.get('categoria', '').strip()
        link = request.form.get('link', '').strip()
        destaque = 1 if request.form.get('destaque') else 0
        imagem_path = None

        if not nome or not link:
            flash('Nome e link são obrigatórios.', 'danger')
            return render_template('form_produto.html', categories=carregar_categorias(), produto=None)

        file = request.files.get('imagem')
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            imagem_path = f'uploads/{filename}'

        db = get_db()
        if hasattr(db, 'cursor') and not hasattr(db, 'row_factory'):
            cur = db.cursor()
            cur.execute(
                'INSERT INTO produtos (nome, descricao, categoria, imagem, link, destaque) VALUES (%s, %s, %s, %s, %s, %s)',
                (nome, descricao, categoria, imagem_path, link, destaque)
            )
            db.commit()
            cur.close()
        else:
            db.execute(
                'INSERT INTO produtos (nome, descricao, categoria, imagem, link, destaque) VALUES (?, ?, ?, ?, ?, ?)',
                (nome, descricao, categoria, imagem_path, link, destaque)
            )
            db.commit()

        flash('Produto adicionado com sucesso!', 'success')
        return redirect(url_for('admin'))

    return render_template('form_produto.html', categories=carregar_categorias(), produto=None)


@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_produto(id):
    db = get_db()
    if hasattr(db, 'cursor') and not hasattr(db, 'row_factory'):
        cur = db.cursor()
        cur.execute('SELECT id, nome, descricao, categoria, imagem, link, destaque FROM produtos WHERE id = %s', (id,))
        r = cur.fetchone()
        cur.close()
        produto = {'id': r[0], 'nome': r[1], 'descricao': r[2], 'categoria': r[3], 'imagem': r[4], 'link': r[5],
                   'destaque': r[6]} if r else None
    else:
        produto = db.execute('SELECT * FROM produtos WHERE id = ?', (id,)).fetchone()

    if not produto:
        flash('Produto não encontrado.', 'danger')
        return redirect(url_for('admin'))

    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        descricao = request.form.get('descricao', '').strip()
        categoria = request.form.get('categoria', '').strip()
        link = request.form.get('link', '').strip()
        destaque = 1 if request.form.get('destaque') else 0
        imagem_path = produto['imagem']

        file = request.files.get('imagem')
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            imagem_path = f'uploads/{filename}'

        if hasattr(db, 'cursor') and not hasattr(db, 'row_factory'):
            cur = db.cursor()
            cur.execute(
                'UPDATE produtos SET nome=%s, descricao=%s, categoria=%s, imagem=%s, link=%s, destaque=%s WHERE id=%s',
                (nome, descricao, categoria, imagem_path, link, destaque, id)
            )
            db.commit()
            cur.close()
        else:
            db.execute(
                'UPDATE produtos SET nome=?, descricao=?, categoria=?, imagem=?, link=?, destaque=? WHERE id=?',
                (nome, descricao, categoria, imagem_path, link, destaque, id)
            )
            db.commit()

        flash('Produto atualizado com sucesso!', 'success')
        return redirect(url_for('admin'))

    return render_template('form_produto.html', categories=carregar_categorias(), produto=produto)


@app.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete_produto(id):
    db = get_db()
    if hasattr(db, 'cursor') and not hasattr(db, 'row_factory'):
        cur = db.cursor()
        cur.execute('DELETE FROM produtos WHERE id = %s', (id,))
        db.commit()
        cur.close()
    else:
        db.execute('DELETE FROM produtos WHERE id = ?', (id,))
        db.commit()
    flash('Produto removido com sucesso!', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/categorias', methods=['GET', 'POST'])
@login_required
def gerenciar_categorias():
    db = get_db()
    if request.method == 'POST':
        nova_cat = request.form.get('nome_categoria', '').strip()
        if nova_cat:
            try:
                if hasattr(db, 'cursor') and not hasattr(db, 'row_factory'):
                    cur = db.cursor()
                    cur.execute('INSERT INTO categorias (nome) VALUES (%s)', (nova_cat,))
                    db.commit()
                    cur.close()
                else:
                    db.execute('INSERT INTO categorias (nome) VALUES (?)', (nova_cat,))
                    db.commit()
                flash(f'Categoria "{nova_cat}" adicionada com sucesso!', 'success')
            except Exception:
                flash('Esta categoria já existe.', 'danger')
        return redirect(url_for('gerenciar_categorias'))

    if hasattr(db, 'cursor') and not hasattr(db, 'row_factory'):
        cur = db.cursor()
        cur.execute('SELECT id, nome FROM categorias ORDER BY nome ASC')
        lista_cru = cur.fetchall()
        cur.close()
        lista_cats = []
        for r in lista_cru:
            lista_cats.append({'id': r[0], 'nome': r[1]})
    else:
        lista_cats = db.execute('SELECT * FROM categorias ORDER BY nome ASC').fetchall()

    return render_template('admin_categorias.html', categories=lista_cats)


@app.route('/admin/categorias/deletar/<int:id>', methods=['POST'])
@login_required
def deletar_categoria(id):
    db = get_db()
    if hasattr(db, 'cursor') and not hasattr(db, 'row_factory'):
        cur = db.cursor()
        cur.execute('SELECT nome FROM categorias WHERE id = %s', (id,))
        cat = cur.fetchone()
        if cat:
            cur.execute('UPDATE produtos SET categoria = \'\' WHERE categoria = %s', (cat[0],))
            cur.execute('DELETE FROM categorias WHERE id = %s', (id,))
            db.commit()
        cur.close()
    else:
        cat = db.execute('SELECT nome FROM categorias WHERE id = ?', (id,)).fetchone()
        if cat:
            db.execute('UPDATE produtos SET categoria = "" WHERE categoria = ?', (cat['nome'],))
            db.execute('DELETE FROM categorias WHERE id = ?', (id,))
            db.commit()
    flash('Categoria removida com sucesso!', 'success')
    return redirect(url_for('gerenciar_categorias'))


os.makedirs(UPLOAD_FOLDER, exist_ok=True)
init_db()

if __name__ == '__main__':
    app.run(debug=True)
else:
    port = int(os.environ.get("PORT", 5000))
    app.config['SERVER_NAME'] = None