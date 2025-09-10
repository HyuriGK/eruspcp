import http.server
import socketserver
import webbrowser
import os
from threading import Timer
import sqlite3
import json
from datetime import datetime, timedelta
import hashlib
import time
from socketserver import ThreadingMixIn
import threading

# Configurações do servidor
PORT = 8000
HOST = "10.1.1.194"
MAIN_HTML_FILE = "prog.acab.html"
FATURAMENTO_HTML_FILE = "faturamento.html"
DASHBOARD_HTML_FILE = "dashboard.html"
CARTEIRA_HTML_FILE = "CARTEIRA.html"
REFUGO_HTML_FILE = "REFUGO.html"
TERCEIRO_HTML_FILE = "terceiro.html"
INVENTARIO_HTML_FILE = "inventario.html"
RAMAIS_HTML_FILE = "ramais.html" # Adicionado
DB_NAME = "programacao_acabamento.db"

class ThreadedTCPServer(ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_NAME, timeout=20)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        try:
            # --- Tabela 'registros' com novos campos para inventário ---
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS registros (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data TEXT,
                    codigo TEXT NOT NULL,
                    op TEXT DEFAULT '',
                    descricao TEXT NOT NULL,
                    quant INTEGER NOT NULL,
                    quant_escariar INTEGER DEFAULT 0,
                    quant_rebarba INTEGER DEFAULT 0,
                    peso REAL,
                    material TEXT DEFAULT '',
                    cliente TEXT DEFAULT '',
                    carga TEXT DEFAULT '',
                    terceiro TEXT DEFAULT '',
                    rebarbar TEXT DEFAULT '',
                    escariar TEXT DEFAULT '',
                    observacoes TEXT DEFAULT '',
                    situacao TEXT DEFAULT 'finalizada',
                    data_finalizacao TEXT DEFAULT '',
                    prioridade TEXT DEFAULT 'baixa',
                    tipo TEXT DEFAULT 'interno',
                    causa TEXT DEFAULT '',
                    setor TEXT DEFAULT '',
                    apontado INTEGER DEFAULT 0,
                    valor REAL DEFAULT 0,
                    ultFaturamento TEXT DEFAULT ''
                )
            ''')

            # Adicionando a coluna 'ultFaturamento' se não existir
            try:
                cursor.execute("ALTER TABLE registros ADD COLUMN ultFaturamento TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass # A coluna já existe, ignora o erro

            # --- Nova tabela para gerenciar itens recebidos ---
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS recebimentos (
                    registro_id INTEGER PRIMARY KEY,
                    carga TEXT NOT NULL,
                    data_recebimento TEXT NOT NULL,
                    FOREIGN KEY (registro_id) REFERENCES registros(id) ON DELETE CASCADE
                )
            ''')

            cursor.execute(''' CREATE TABLE IF NOT EXISTS programacoes ( id INTEGER PRIMARY KEY AUTOINCREMENT, data_criacao TEXT NOT NULL, data_entrega TEXT NOT NULL, arquivo TEXT NOT NULL ) ''')
            cursor.execute(''' CREATE TABLE IF NOT EXISTS programacao_itens ( id INTEGER PRIMARY KEY AUTOINCREMENT, programacao_id INTEGER NOT NULL, registro_id INTEGER NOT NULL, FOREIGN KEY (programacao_id) REFERENCES programacoes(id) ) ''')
            cursor.execute(''' CREATE TABLE IF NOT EXISTS carteira_pedidos ( id INTEGER PRIMARY KEY AUTOINCREMENT, pedido TEXT NOT NULL, entrega TEXT NOT NULL, razao_social TEXT NOT NULL, codigo TEXT NOT NULL, nome_produto TEXT NOT NULL, material TEXT NOT NULL, saldo REAL NOT NULL, peso_un REAL NOT NULL, peso_total REAL NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ) ''')

            # --- Nova tabela para ramais ---
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ramais (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    ramal TEXT NOT NULL
                )
            ''')
            
            # Popula a tabela de ramais com dados iniciais se estiver vazia
            cursor.execute('SELECT COUNT(*) FROM ramais')
            if cursor.fetchone()[0] == 0:
                dados_iniciais_ramais = [
                    ('ALESSANDRA', '210'), ('ALMOXARIFADO', '206'), ('EDUARDA', '201'),
                    ('ELISANGELA', '202'), ('GIOVANI FELIX', '208'), ('HUMBERTO', '211'),
                    ('ISAAC', '209'), ('JADSON', '205'), ('LABORATORIO', '207'),
                    ('LAYANE', '200'), ('LUIS', '203'), ('ROBISON', '204')
                ]
                cursor.executemany('INSERT INTO ramais (nome, ramal) VALUES (?, ?)', dados_iniciais_ramais)

            self.conn.commit()
        except sqlite3.Error as e:
            print(f"Erro ao criar tabelas: {e}")

    def close(self):
        if hasattr(self, 'conn'):
            self.conn.close()

    # Métodos para Ramais
    def get_all_ramais(self):
        cursor = self.conn.cursor()
        try:
            cursor.execute('SELECT * FROM ramais ORDER BY nome ASC')
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            print(f"Erro ao buscar ramais: {e}")
            return []

    def add_ramal(self, data):
        cursor = self.conn.cursor()
        try:
            cursor.execute('INSERT INTO ramais (nome, ramal) VALUES (?, ?)', (data['nome'], data['ramal']))
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            print(f"Erro ao adicionar ramal: {e}")
            return None

    def delete_ramal(self, ramal_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute('DELETE FROM ramais WHERE id = ?', (ramal_id,))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Erro ao excluir ramal: {e}")
            return False
            
    def get_all_registros(self):
        cursor = self.conn.cursor()
        try:
            cursor.execute('SELECT * FROM registros ORDER BY data DESC')
            columns = [column[0] for column in cursor.description]
            registros = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return registros
        except sqlite3.Error as e:
            print(f"Erro ao buscar registros: {e}")
            return []
    
    def add_registro(self, registro):
        cursor = self.conn.cursor()
        try:
            campos_obrigatorios = ['codigo', 'descricao', 'quant']
            for campo in campos_obrigatorios:
                if campo not in registro:
                    print(f"Campo obrigatório faltando: {campo}")
                    return None
            
            cursor.execute('''
                INSERT INTO registros (
                    data, codigo, op, descricao, quant, quant_escariar, quant_rebarba,
                    peso, material, cliente, carga, terceiro, rebarbar, escariar, 
                    observacoes, situacao, data_finalizacao, prioridade, tipo, causa, setor, apontado, valor, ultFaturamento
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                registro.get('data', ''), # Adicionado .get() para não ser obrigatório
                registro['codigo'],
                registro.get('op', ''),
                registro['descricao'],
                registro['quant'],
                registro.get('quant_escariar', 0),
                registro.get('quant_rebarba', 0),
                registro.get('peso', 0),
                registro.get('material', ''),
                registro.get('cliente', ''),
                registro.get('carga', ''),      
                registro.get('terceiro', ''),   
                registro.get('rebarbar', ''),
                registro.get('escariar', ''),
                registro.get('observacoes', ''),
                registro.get('situacao', 'finalizada'),
                registro.get('dataFinalizacao', ''),
                registro.get('prioridade', 'baixa'),
                registro.get('tipo', 'interno'),
                registro.get('causa', ''),
                registro.get('setor', ''),
                registro.get('apontado', 0),
                registro.get('valor', 0),
                registro.get('ultFaturamento', '')
            ))
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            print(f"Erro ao adicionar registro: {e}")
            return None
        except Exception as e:
            print(f"Erro inesperado ao adicionar registro: {e}")
            return None
    
    def update_registro(self, registro_id, updates):
        cursor = self.conn.cursor()
        try:
            if not updates:
                return False
            set_clause = ', '.join([f"{key} = ?" for key in updates.keys()])
            values = list(updates.values())
            values.append(registro_id)
            cursor.execute(f'UPDATE registros SET {set_clause} WHERE id = ?', values)
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Erro ao atualizar registro: {e}")
            return False
    
    def delete_registro(self, registro_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute('DELETE FROM registros WHERE id = ?', (registro_id,))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Erro ao excluir registro: {e}")
            return False

    def get_faturamento_registros(self):
        cursor = self.conn.cursor()
        try:
            cursor.execute('SELECT * FROM registros WHERE tipo = "faturamento" ORDER BY data DESC')
            columns = [column[0] for column in cursor.description]
            registros = []
            
            for row in cursor.fetchall():
                registro = dict(zip(columns, row))
                registro['peso_total'] = registro['peso'] * registro['quant']
                registros.append(registro)
            
            return registros
        except sqlite3.Error as e:
            print(f"Erro ao buscar registros de faturamento: {e}")
            return []
    
    def get_refugo_registros(self):
        cursor = self.conn.cursor()
        try:
            cursor.execute('SELECT * FROM registros WHERE tipo = "refugo" ORDER BY data DESC')
            columns = [column[0] for column in cursor.description]
            registros = []
            
            for row in cursor.fetchall():
                registro = dict(zip(columns, row))
                registro['peso_total'] = registro['peso'] * registro['quant']
                registros.append(registro)
            
            return registros
        except sqlite3.Error as e:
            print(f"Erro ao buscar registros de refugo: {e}")
            return []
    
    def get_inventario_registros(self):
        cursor = self.conn.cursor()
        try:
            cursor.execute('SELECT * FROM registros WHERE tipo = "estoque" ORDER BY codigo ASC')
            columns = [column[0] for column in cursor.description]
            registros = []
            
            for row in cursor.fetchall():
                registro = dict(zip(columns, row))
                registro['peso_total'] = registro['peso'] * registro['quant']
                registros.append(registro)
            
            return registros
        except sqlite3.Error as e:
            print(f"Erro ao buscar registros de inventário: {e}")
            return []

    def get_carteira_pedidos(self):
        cursor = self.conn.cursor()
        try:
            cursor.execute('SELECT * FROM carteira_pedidos ORDER BY created_at DESC')
            columns = [column[0] for column in cursor.description]
            pedidos = []
            
            for row in cursor.fetchall():
                pedidos.append(dict(zip(columns, row)))
            
            return pedidos
        except sqlite3.Error as e:
            print(f"Erro ao buscar pedidos da carteira: {e}")
            return []
            
    def save_programacao(self, data_entrega, arquivo, itens):
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO programacoes (data_criacao, data_entrega, arquivo)
                VALUES (?, ?, ?)
            ''', (
                datetime.now().isoformat(),
                data_entrega,
                arquivo
            ))
            programacao_id = cursor.lastrowid
            
            for item_id in itens:
                cursor.execute('''
                    INSERT INTO programacao_itens (programacao_id, registro_id)
                    VALUES (?, ?)
                ''', (programacao_id, item_id))
            
            self.conn.commit()
            return programacao_id
        except sqlite3.Error as e:
            print(f"Erro ao salvar programação: {e}")
            return None
    
    def save_carteira_pedidos(self, pedidos):
        cursor = self.conn.cursor()
        try:
            cursor.execute('DELETE FROM carteira_pedidos')
            
            for pedido in pedidos:
                cursor.execute('''
                    INSERT INTO carteira_pedidos 
                    (pedido, entrega, razao_social, codigo, nome_produto, material, saldo, peso_un, peso_total)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    pedido.get('pedido', ''),
                    pedido.get('entrega', ''),
                    pedido.get('razao_social', ''),
                    pedido.get('codigo', ''),
                    pedido.get('nome_produto', ''),
                    pedido.get('material', ''),
                    pedido.get('saldo', 0),
                    pedido.get('peso_un', 0),
                    pedido.get('peso_total', 0)
                ))
            
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Erro ao salvar carteira de pedidos: {e}")
            return False

    def add_recebimento(self, registro_id, carga):
        cursor = self.conn.cursor()
        try:
            cursor.execute('INSERT OR IGNORE INTO recebimentos (registro_id, carga, data_recebimento) VALUES (?, ?, ?)',
                           (registro_id, carga, datetime.now().isoformat()))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Erro ao adicionar recebimento: {e}")
            return False

    def remove_recebimento(self, registro_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute('DELETE FROM recebimentos WHERE registro_id = ?', (registro_id,))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Erro ao remover recebimento: {e}")
            return False

    def get_recebimentos(self):
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                SELECT 
                    r.id, 
                    r.codigo, 
                    r.descricao, 
                    r.quant, 
                    r.carga,
                    r.terceiro
                FROM registros r
                JOIN recebimentos rec ON r.id = rec.registro_id
                ORDER BY rec.data_recebimento DESC
            ''')
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            print(f"Erro ao buscar recebimentos: {e}")
            return []

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.db = Database()
        super().__init__(*args, directory=os.getcwd(), **kwargs)
    
    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionAbortedError, ConnectionResetError) as e:
            print(f"Connection error: {e}")
        finally:
            if hasattr(self, 'db'):
                self.db.close()
    
    def do_GET(self):
        if self.path == '/':
            self.path = f'/{MAIN_HTML_FILE}' if os.path.exists(MAIN_HTML_FILE) else self.send_error(404, "Arquivo principal não encontrado")
        elif self.path == '/faturamento':
            self.path = f'/{FATURAMENTO_HTML_FILE}' if os.path.exists(FATURAMENTO_HTML_FILE) else self.send_error(404, "Página de faturamento não encontrada")
        elif self.path == '/dashboard':
            self.path = f'/{DASHBOARD_HTML_FILE}' if os.path.exists(DASHBOARD_HTML_FILE) else self.send_error(404, "Página de dashboard não encontrada")
        elif self.path == '/carteira':
            self.path = f'/{CARTEIRA_HTML_FILE}' if os.path.exists(CARTEIRA_HTML_FILE) else self.send_error(404, "Página de carteira não encontrada")
        elif self.path == '/refugo':
            self.path = f'/{REFUGO_HTML_FILE}' if os.path.exists(REFUGO_HTML_FILE) else self.send_error(404, "Página de refugo não encontrada")
        elif self.path == '/terceiro':
            self.path = f'/{TERCEIRO_HTML_FILE}' if os.path.exists(TERCEIRO_HTML_FILE) else self.send_error(404, "Página de terceiro não encontrada")
        elif self.path == '/inventario':
            self.path = f'/{INVENTARIO_HTML_FILE}' if os.path.exists(INVENTARIO_HTML_FILE) else self.send_error(404, "Página de inventário não encontrada")
        elif self.path == '/ramais': # Rota para a nova página de ramais
            self.path = f'/{RAMAIS_HTML_FILE}' if os.path.exists(RAMAIS_HTML_FILE) else self.send_error(404, "Página de ramais não encontrada")
        elif self.path == '/api/registros':
            self.handle_get_registros()
            return
        elif self.path == '/api/faturamento':
            self.handle_get_faturamento()
            return
        elif self.path == '/api/refugo':
            self.handle_get_refugo()
            return
        elif self.path == '/api/inventario':
            self.handle_get_inventario()
            return
        elif self.path == '/api/carteira':
            self.handle_get_carteira()
            return
        elif self.path == '/api/recebidos':
            self.handle_get_recebidos()
            return
        elif self.path == '/api/ramais': # API para buscar ramais
            self.handle_get_ramais()
            return
        
        return http.server.SimpleHTTPRequestHandler.do_GET(self)

    # Handlers para Ramais
    def handle_get_ramais(self):
        ramais = self.db.get_all_ramais()
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(ramais).encode('utf-8'))
        
    def handle_get_registros(self):
        registros = self.db.get_all_registros()
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(registros).encode('utf-8'))
    
    def handle_get_faturamento(self):
        registros = self.db.get_faturamento_registros()
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(registros).encode('utf-8'))
    
    def handle_get_refugo(self):
        registros = self.db.get_refugo_registros()
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(registros).encode('utf-8'))
    
    def handle_get_inventario(self):
        registros = self.db.get_inventario_registros()
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(registros).encode('utf-8'))

    def handle_get_carteira(self):
        pedidos = self.db.get_carteira_pedidos()
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(pedidos).encode('utf-8'))

    def handle_get_recebidos(self):
        recebimentos = self.db.get_recebimentos()
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(recebimentos).encode('utf-8'))
    
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length > 1024 * 1024:
            self.send_error(413, "Request too large")
            return
            
        if self.path == '/api/registros':
            self.handle_post_registros()
        elif self.path == '/api/inventario-add':
            self.handle_post_inventario()
        elif self.path == '/api/update':
            self.handle_update_registro()
        elif self.path == '/api/delete':
            self.handle_delete_registro()
        elif self.path == '/api/inventario-update':
            self.handle_update_inventario()
        elif self.path == '/api/inventario-delete':
            self.handle_delete_inventario()
        elif self.path == '/api/save-programacao':
            self.handle_save_programacao()
        elif self.path == '/api/save-carteira':
            self.handle_save_carteira()
        elif self.path == '/api/recebidos':
            self.handle_post_recebidos()
        elif self.path == '/api/ramais': # API para adicionar ramal
            self.handle_post_ramal()
        elif self.path == '/api/ramais-delete': # API para deletar ramal
            self.handle_delete_ramal()
        else:
            self.send_response(404)
            self.end_headers()
    
    # Handlers POST para Ramais
    def handle_post_ramal(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        ramal_id = self.db.add_ramal(data)
        
        if ramal_id:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'id': ramal_id}).encode('utf-8'))
        else:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': False, 'error': 'Erro ao adicionar ramal'}).encode('utf-8'))

    def handle_delete_ramal(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        ramal_id = data.get('id')
        
        if ramal_id:
            success = self.db.delete_ramal(ramal_id)
            response = {'success': success}
        else:
            response = {'success': False, 'error': 'ID não fornecido'}
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))

    def handle_post_registros(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        registro = json.loads(post_data.decode('utf-8'))
        
        registro_id = self.db.add_registro(registro)
        
        if registro_id:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'id': registro_id}).encode('utf-8'))
        else:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': False, 'error': 'Erro ao adicionar registro'}).encode('utf-8'))

    def handle_post_inventario(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        item = json.loads(post_data.decode('utf-8'))
        
        item['tipo'] = 'estoque'
        
        item_id = self.db.add_registro(item)
        
        if item_id:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True, 'id': item_id}).encode('utf-8'))
        else:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': False, 'error': 'Erro ao adicionar item de estoque'}).encode('utf-8'))
    
    def handle_update_registro(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        registro_id = data.get('id')
        updates = data.get('updates', {})
        
        if registro_id and updates:
            if updates.get('situacao') == 'finalizada' and 'data_finalizacao' not in updates:
                updates['data_finalizacao'] = datetime.now().strftime('%Y-%m-%d')
            
            success = self.db.update_registro(registro_id, updates)
            response = {'success': success}
        else:
            response = {'success': False, 'error': 'Dados inválidos'}
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))

    def handle_update_inventario(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        registro_id = data.get('id')
        updates = data.get('updates', {})
        
        if registro_id and updates:
            success = self.db.update_registro(registro_id, updates)
            response = {'success': success}
        else:
            response = {'success': False, 'error': 'Dados inválidos'}
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))

    def handle_delete_registro(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        registro_id = data.get('id')
        
        if registro_id:
            success = self.db.delete_registro(registro_id)
            response = {'success': success}
        else:
            response = {'success': False, 'error': 'ID não fornecido'}
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))

    def handle_delete_inventario(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        registro_id = data.get('id')
        
        if registro_id:
            success = self.db.delete_registro(registro_id)
            response = {'success': success}
        else:
            response = {'success': False, 'error': 'ID não fornecido'}
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))
    
    def handle_save_programacao(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        data_entrega = data.get('data_entrega')
        itens = data.get('itens', [])
        nome_arquivo = data.get('nome_arquivo')
        
        if data_entrega and len(itens) > 0 and nome_arquivo:
            if not os.path.exists('prog'):
                os.makedirs('prog')
            
            programacao_id = self.db.save_programacao(data_entrega, nome_arquivo, itens)
            
            if programacao_id:
                response = {'success': True, 'id': programacao_id}
            else:
                response = {'success': False, 'error': 'Erro ao salvar programação'}
        else:
            response = {'success': False, 'error': 'Dados inválidos'}
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))
    
    def handle_save_carteira(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        if data and isinstance(data, list):
            success = self.db.save_carteira_pedidos(data)
            response = {'success': success}
        else:
            response = {'success': False, 'error': 'Dados inválidos'}
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))

    def handle_post_recebidos(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8'))
        
        registro_id = data.get('id')
        carga = data.get('carga')
        is_checked = data.get('checked')
        
        if registro_id and carga is not None and is_checked is not None:
            if is_checked:
                success = self.db.add_recebimento(registro_id, carga)
            else:
                success = self.db.remove_recebimento(registro_id)
            response = {'success': success}
        else:
            response = {'success': False, 'error': 'Dados inválidos'}
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))
    
    def log_message(self, format, *args):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = "%s - - [%s] %s" % (
            self.address_string(),
            timestamp,
            format % args
        )
        print(message)

def run_server():
    html_files = {
        'Principal': MAIN_HTML_FILE,
        'Faturamento': FATURAMENTO_HTML_FILE,
        'Dashboard': DASHBOARD_HTML_FILE,
        'Carteira': CARTEIRA_HTML_FILE,
        'Refugo': REFUGO_HTML_FILE,
        'Terceiro': TERCEIRO_HTML_FILE,
        'Inventário': INVENTARIO_HTML_FILE,
        'Ramais': RAMAIS_HTML_FILE, # Adicionado
    }
    
    for name, file in html_files.items():
        if not os.path.exists(file):
            print(f"AVISO: Arquivo {file} ({name}) não encontrado no diretório atual")
    
    db = Database()
    db.create_tables()
    db.close()
    
    with ThreadedTCPServer((HOST, PORT), Handler) as httpd:
        print(f"Servidor rodando em http://{HOST}:{PORT}")
        print(f"Acesse: http://{HOST}:{PORT} (Programação de Acabamento)")
        print(f"Acesse: http://{HOST}:{PORT}/faturamento (Faturamento)")
        print(f"Acesse: http://{HOST}:{PORT}/dashboard (Dashboard)")
        print(f"Acesse: http://{HOST}:{PORT}/carteira (Carteira)")
        print(f"Acesse: http://{HOST}:{PORT}/refugo (Refugo)")
        print(f"Acesse: http://{HOST}:{PORT}/terceiro (Terceiro)")
        print(f"Acesse: http://{HOST}:{PORT}/inventario (Inventário)")
        print(f"Acesse: http://{HOST}:{PORT}/ramais (Ramais)") # Adicionado
        
        try:
            webbrowser.open(f"http://{HOST}:{PORT}/dashboard")
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServidor encerrado")
        finally:
            httpd.server_close()

if __name__ == "__main__":
    run_server()