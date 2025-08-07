from sqlalchemy import text
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
import os
from datetime import datetime
import random  # 用于生成随机颜色

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///forklift.db'
db = SQLAlchemy(app)

# 数据库模型
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    points = db.Column(db.Integer, default=100)  # 注册赠送100分
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    price = db.Column(db.Integer, nullable=False)  # 阅读价格（≥100分）
    status = db.Column(db.String(20), default='pending')  # pending/approved/rejected
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    read_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author = db.relationship('User', backref=db.backref('documents', lazy=True))

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'))
    amount = db.Column(db.Integer, nullable=False)
    transaction_type = db.Column(db.String(20))  # read/reward/fee (避免使用type关键字)
    description = db.Column(db.String(100))  # 交易描述
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref=db.backref('transactions', lazy=True))

# 评论模型（修复字段名冲突）
class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False, default='')  # 添加默认值
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # 评论类型：comment-普通评论，like-点赞，dislike-差评（避免使用type关键字）
    comment_type = db.Column(db.String(20), default='comment')
    
    user = db.relationship('User', backref=db.backref('comments', lazy=True))
    document = db.relationship('Document', backref=db.backref('comments', lazy=True))

# 社区动态模型
class CommunityPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref=db.backref('community_posts', lazy=True))

# 系统统计表
class SystemStats(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    total_points_created = db.Column(db.Integer, default=0)  # 系统创建的总积分
    total_fees_collected = db.Column(db.Integer, default=0)  # 收取的总手续费
    total_rewards_given = db.Column(db.Integer, default=0)  # 发放的总奖励

# 需求模型
class Demand(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    demand_type = db.Column(db.String(20))  # service/parts
    points_required = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='active')  # active/completed
    contact_info = db.Column(db.String(100))
    
    user = db.relationship('User', backref=db.backref('demands', lazy=True))

# 创建数据库
with app.app_context():
    db.create_all()
    # 初始化系统统计
    if not SystemStats.query.first():
        db.session.add(SystemStats())
        db.session.commit()

# 实用函数
def calculate_bonus(read_count):
    """计算阅读量奖励"""
    base = 10
    bonus = min(base + (read_count // 100), 100)  # 最高100分
    return bonus

# 模板辅助函数
@app.context_processor
def utility_processor():
    def get_random_color():
        colors = ['#e3f2fd', '#fff8e1', '#f1f8e9', '#fce4ec', '#e8f5e9']
        return random.choice(colors)
    return dict(get_random_color=get_random_color)

# ========== 路由定义 ==========
@app.route('/')
def home():
    """首页 - 显示已审核文档"""
    try:
        documents = Document.query.filter_by(status='approved').all()
        
        # 获取最新社区动态
        community_posts = CommunityPost.query.order_by(CommunityPost.created_at.desc()).limit(10).all()
        
        # 获取最新需求
        latest_demands = Demand.query.filter_by(status='active').order_by(Demand.created_at.desc()).limit(5).all()
        
        return render_template('index.html', 
                              documents=documents, 
                              community_posts=community_posts,
                              latest_demands=latest_demands)
    except Exception as e:
        app.logger.error(f"首页错误: {str(e)}")
        # 提供降级内容而不是完全失败
        return render_template('index.html', documents=[], community_posts=[], latest_demands=[])

@app.route('/register', methods=['GET', 'POST'])
def register():
    """用户注册"""
    try:
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()
            
            if not username or not password:
                flash('用户名和密码不能为空', 'danger')
                return redirect(url_for('register'))
            
            if User.query.filter_by(username=username).first():
                flash('用户名已存在', 'danger')
                return redirect(url_for('register'))
            
            new_user = User(username=username, password=password)
            db.session.add(new_user)
            db.session.commit()
            
            flash('注册成功！获得100初始积分', 'success')
            return redirect(url_for('login'))
        
        return render_template('register.html')
    except Exception as e:
        db.session.rollback()
        print(f"注册错误: {str(e)}")
        flash('注册过程中出错，请重试', 'danger')
        return redirect(url_for('register'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """用户登录"""
    try:
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()
            
            if not username or not password:
                flash('请输入用户名和密码', 'danger')
                return redirect(url_for('login'))
            
            user = User.query.filter_by(username=username, password=password).first()
            
            if user:
                session['user_id'] = user.id
                session['username'] = user.username
                return redirect(url_for('dashboard'))
            
            flash('用户名或密码错误', 'danger')
        
        return render_template('login.html')
    except Exception as e:
        print(f"登录错误: {str(e)}")
        flash('登录过程中出错，请重试', 'danger')
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    """用户登出"""
    try:
        session.pop('user_id', None)
        session.pop('username', None)
        return redirect(url_for('home'))
    except Exception as e:
        print(f"登出错误: {str(e)}")
        return redirect(url_for('home'))

@app.route('/dashboard')
def dashboard():
    """用户仪表盘"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        user = User.query.get(session['user_id'])
        if not user:
            flash('用户不存在', 'danger')
            return redirect(url_for('login'))
        
        user_docs = Document.query.filter_by(author_id=user.id).all()
        
        # 计算统计信息
        total_reads = sum(doc.read_count for doc in user_docs)
        
        # 计算总积分（简化处理，实际应从交易记录获取）
        total_points = user.points
        
        # 计算点赞数（简化处理）
        total_likes = 0
        for doc in user_docs:
            total_likes += Comment.query.filter_by(document_id=doc.id, comment_type='like').count()
        
        # 添加调试信息
        print(f"用户仪表盘: 用户={user.username}, 文档数={len(user_docs)}")
        
        return render_template('dashboard.html', 
                              user=user, 
                              user_docs=user_docs,
                              total_reads=total_reads,
                              total_points=total_points,
                              total_likes=total_likes)
    except Exception as e:
        # 记录错误日志
        print(f"仪表盘错误: {str(e)}")
        flash('服务器内部错误，请稍后再试', 'danger')
        return redirect(url_for('home'))

@app.route('/submit_document', methods=['GET', 'POST'])
def submit_document():
    """提交技术文档"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        if request.method == 'POST':
            # 获取表单数据并验证
            title = request.form.get('title', '').strip()
            content = request.form.get('content', '').strip()
            price = request.form.get('price', '100')
            
            # 验证必要字段
            if not title or not content:
                flash('标题和内容不能为空', 'danger')
                return redirect(url_for('submit_document'))
            
            try:
                price = int(price)
            except ValueError:
                price = 100
            
            if price < 100:
                flash('阅读价格不能低于100分', 'danger')
                return redirect(url_for('submit_document'))
            
            # 创建新文档
            new_doc = Document(
                title=title,
                content=content,
                price=price,
                author_id=session['user_id'],
                status='pending'
            )
            
            # 保存到数据库
            db.session.add(new_doc)
            db.session.commit()
            
            flash('文档已提交，等待审核', 'success')
            return redirect(url_for('dashboard'))
        
        return render_template('submit_document.html')
    
    except Exception as e:
        # 回滚数据库操作
        db.session.rollback()
        print(f"提交文档错误: {str(e)}")
        flash(f'提交文档时出错: {str(e)}', 'danger')
        return redirect(url_for('submit_document'))

@app.route('/document/<int:doc_id>')
def view_document(doc_id):
    """查看文档详情（付费阅读）"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        doc = Document.query.get_or_404(doc_id)
        user = User.query.get(session['user_id'])
        
        # 计算评论统计数据
        likes_count = Comment.query.filter_by(document_id=doc_id, comment_type='like').count()
        dislikes_count = Comment.query.filter_by(document_id=doc_id, comment_type='dislike').count()
        comments_count = Comment.query.filter_by(document_id=doc_id, comment_type='comment').count()
        
        # 检查当前用户是否已经点赞/差评
        user_liked = Comment.query.filter_by(
            document_id=doc_id, 
            user_id=session['user_id'], 
            comment_type='like'
        ).first() is not None
        
        user_disliked = Comment.query.filter_by(
            document_id=doc_id, 
            user_id=session['user_id'], 
            comment_type='dislike'
        ).first() is not None
        
        # 检查是否已购买
        if Transaction.query.filter_by(
            user_id=user.id, 
            document_id=doc.id,
            transaction_type='read'
        ).first():
            return render_template('document_detail.html', 
                                  document=doc, 
                                  content=doc.content,
                                  likes_count=likes_count,
                                  dislikes_count=dislikes_count,
                                  comments_count=comments_count,
                                  user_liked=user_liked,
                                  user_disliked=user_disliked)
        
        # 检查积分是否足够
        if user.points < doc.price:
            flash('积分不足，无法阅读', 'danger')
            return redirect(url_for('dashboard'))
        
        return render_template('document_detail.html', 
                              document=doc,
                              likes_count=likes_count,
                              dislikes_count=dislikes_count,
                              comments_count=comments_count,
                              user_liked=user_liked,
                              user_disliked=user_disliked)
    except Exception as e:
        print(f"查看文档错误: {str(e)}")
        flash('加载文档时出错', 'danger')
        return redirect(url_for('home'))

@app.route('/purchase_document/<int:doc_id>', methods=['POST'])
def purchase_document(doc_id):
    """购买文档阅读权限（含10%手续费）"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        doc = Document.query.get_or_404(doc_id)
        user = User.query.get(session['user_id'])
        stats = SystemStats.query.first()
        
        if user.points < doc.price:
            flash('积分不足', 'danger')
            return redirect(url_for('view_document', doc_id=doc.id))
        
        # 计算手续费和作者所得
        platform_fee = max(1, int(doc.price * 0.1))  # 至少1分
        author_earnings = doc.price - platform_fee
        
        # 扣除读者积分
        user.points -= doc.price
        
        # 奖励作者积分
        author = User.query.get(doc.author_id)
        author.points += author_earnings
        
        # 记录交易
        fee_transaction = Transaction(
            user_id=user.id,
            document_id=doc.id,
            amount=-platform_fee,
            transaction_type='fee',
            description=f'平台手续费 ({doc.price}的10%)'
        )
        
        author_transaction = Transaction(
            user_id=author.id,
            document_id=doc.id,
            amount=author_earnings,
            transaction_type='read',
            description=f'文档收入 (扣除{platform_fee}手续费)'
        )
        
        # 更新阅读计数
        doc.read_count += 1
        
        # 更新系统统计
        stats.total_fees_collected += platform_fee
        
        # 检查阅读量奖励
        if doc.read_count % 100 == 0:
            bonus = calculate_bonus(doc.read_count)
            author.points += bonus
            stats.total_rewards_given += bonus
            
            bonus_transaction = Transaction(
                user_id=author.id,
                document_id=doc.id,
                amount=bonus,
                transaction_type='reward',
                description=f'阅读量达到{doc.read_count}奖励'
            )
            db.session.add(bonus_transaction)
        
        db.session.add(fee_transaction)
        db.session.add(author_transaction)
        db.session.commit()
        
        flash(f'成功支付{doc.price}积分（含{platform_fee}平台手续费）', 'success')
        return redirect(url_for('view_document', doc_id=doc.id))
    except Exception as e:
        db.session.rollback()
        print(f"购买文档错误: {str(e)}")
        flash('购买文档时出错，请重试', 'danger')
        return redirect(url_for('view_document', doc_id=doc_id))

# 添加评论路由
@app.route('/add_comment/<int:doc_id>', methods=['POST'])
def add_comment(doc_id):
    """添加评论"""
    if 'user_id' not in session:
        flash('请先登录', 'danger')
        return redirect(url_for('login'))
    
    try:
        comment_type = request.form.get('comment_type', 'comment')  # 修改为 comment_type
        content = request.form.get('content', '')
        
        # 如果是点赞或差评，不需要内容
        if comment_type == 'comment' and not content.strip():
            flash('评论内容不能为空', 'danger')
            return redirect(url_for('view_document', doc_id=doc_id))
        
        new_comment = Comment(
            content=content,
            document_id=doc_id,
            user_id=session['user_id'],
            comment_type=comment_type  # 修改为 comment_type
        )
        
        db.session.add(new_comment)
        db.session.commit()
        
        flash('操作成功', 'success')
        return redirect(url_for('view_document', doc_id=doc_id))
    except Exception as e:
        db.session.rollback()
        print(f"添加评论错误: {str(e)}")
        flash('添加评论时出错', 'danger')
        return redirect(url_for('view_document', doc_id=doc_id))

@app.route('/get_comments/<int:doc_id>')
def get_comments(doc_id):
    """获取文档评论（JSON格式）"""
    try:
        comments = Comment.query.filter_by(document_id=doc_id).order_by(Comment.created_at.desc()).all()
        
        comments_data = []
        for comment in comments:
            comments_data.append({
                'id': comment.id,
                'content': comment.content,
                'username': comment.user.username,
                'comment_type': comment.comment_type,  # 修改为 comment_type
                'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M'),
                'avatar': f"https://ui-avatars.com/api/?name={comment.user.username}&background=random"
            })
        
        return jsonify(comments_data)
    except Exception as e:
        print(f"获取评论错误: {str(e)}")
        return jsonify({'error': '获取评论失败'}), 500

@app.route('/admin/documents')
def admin_documents_list():
    """管理后台 - 文档审核"""
    try:
        pending_docs = Document.query.filter_by(status='pending').all()
        return render_template('admin_documents.html', documents=pending_docs)
    except Exception as e:
        print(f"审核列表错误: {str(e)}")
        flash('加载审核列表时出错', 'danger')
        return redirect(url_for('admin_dashboard'))

@app.route('/approve_document/<int:doc_id>')
def approve_document(doc_id):
    """批准文档并奖励作者"""
    try:
        doc = Document.query.get_or_404(doc_id)
        author = User.query.get(doc.author_id)
        stats = SystemStats.query.first()
        
        # 根据文档质量确定奖励（这里简化处理）
        reward = min(50, stats.total_fees_collected // 10)  # 奖励不超过手续费池的10%
        reward = max(10, min(reward, 100))  # 限制在10-100分之间
        
        if reward > stats.total_fees_collected:
            # 如果手续费池不足，使用系统创建积分
            author.points += reward
            stats.total_points_created += reward
            source = "系统创建"
        else:
            # 使用手续费池奖励
            author.points += reward
            stats.total_fees_collected -= reward
            stats.total_rewards_given += reward
            source = "手续费池"
        
        # 记录交易
        reward_transaction = Transaction(
            user_id=author.id,
            document_id=doc.id,
            amount=reward,
            transaction_type='reward',
            description=f'文档审核奖励 ({source})'
        )
        
        doc.status = 'approved'
        
        db.session.add(reward_transaction)
        db.session.commit()
        
        flash(f'文档已批准，作者获得{reward}分奖励（来源: {source}）', 'success')
        return redirect(url_for('admin_documents_list'))
    except Exception as e:
        db.session.rollback()
        print(f"批准文档错误: {str(e)}")
        flash('批准文档时出错', 'danger')
        return redirect(url_for('admin_documents_list'))

@app.route('/reject_document/<int:doc_id>')
def reject_document(doc_id):
    """拒绝文档"""
    try:
        doc = Document.query.get_or_404(doc_id)
        doc.status = 'rejected'
        db.session.commit()
        flash('文档已拒绝', 'info')
        return redirect(url_for('admin_documents_list'))
    except Exception as e:
        db.session.rollback()
        print(f"拒绝文档错误: {str(e)}")
        flash('拒绝文档时出错', 'danger')
        return redirect(url_for('admin_documents_list'))

@app.route('/system_stats')
def system_stats():
    """系统统计页面"""
    try:
        stats = SystemStats.query.first()
        users = User.query.count()
        documents = Document.query.filter_by(status='approved').count()
        
        # 计算积分流通情况
        total_points_in_circulation = db.session.query(db.func.sum(User.points)).scalar() or 0
        points_created = stats.total_points_created
        fees_collected = stats.total_fees_collected
        rewards_given = stats.total_rewards_given
        
        # 计算系统依赖度
        if points_created > 0:
            system_dependency = fees_collected / (points_created + fees_collected) * 100
        else:
            system_dependency = 0.0
        
        return render_template('system_stats.html', 
                              stats=stats,
                              users=users,
                              documents=documents,
                              total_points=total_points_in_circulation,
                              system_dependency=f"{system_dependency:.2f}%")
    except Exception as e:
        print(f"系统统计错误: {str(e)}")
        flash('加载系统统计时出错', 'danger')
        return redirect(url_for('home'))

@app.route('/admin')
def admin_dashboard():
    """管理员仪表盘"""
    try:
        pending_docs = Document.query.filter_by(status='pending').count()
        stats = SystemStats.query.first()
        return render_template('admin_dashboard.html', 
                              pending_docs=pending_docs,
                              stats=stats)
    except Exception as e:
        print(f"管理员仪表盘错误: {str(e)}")
        flash('加载管理员仪表盘时出错', 'danger')
        return redirect(url_for('home'))

# ========== 新增功能路由 ==========

# 系统状态检查API
@app.route('/api/system_status')
def system_status():
    """检查系统状态"""
    try:
        # 简单检查数据库连接
        db.session.execute('SELECT 1')
        return jsonify({'status': 'good'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# 平台文档列表
@app.route('/platform_docs')
def platform_docs():
    """平台文档列表（排除当前用户自己的文档）"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        # 获取已批准的非当前用户文档
        docs = Document.query.filter(
            Document.status == 'approved',
            Document.author_id != session['user_id']
        ).all()
        
        return render_template('platform_docs.html', documents=docs)
    except Exception as e:
        print(f"平台文档列表错误: {str(e)}")
        flash('加载平台文档时出错', 'danger')
        return redirect(url_for('dashboard'))

# 需求列表
@app.route('/demands')
def demand_list():
    """需求列表页面"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        # 获取所有活跃需求
        demands = Demand.query.filter_by(status='active').all()
        
        # 计算需求统计
        service_demands = Demand.query.filter_by(
            status='active', 
            demand_type='service'
        ).count()
        
        parts_demands = Demand.query.filter_by(
            status='active', 
            demand_type='parts'
        ).count()
        
        return render_template('demands.html', 
                              demands=demands,
                              service_demands=service_demands,
                              parts_demands=parts_demands)
    except Exception as e:
        print(f"需求列表错误: {str(e)}")
        flash('加载需求列表时出错', 'danger')
        return redirect(url_for('dashboard'))

# 需求详情
@app.route('/demand_detail/<int:demand_id>')
def demand_detail(demand_id):
    """需求详情页面"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        demand = Demand.query.get_or_404(demand_id)
        return render_template('demand_detail.html', demand=demand)
    except Exception as e:
        print(f"需求详情错误: {str(e)}")
        flash('加载需求详情时出错', 'danger')
        return redirect(url_for('demand_list'))

# 发布新需求
@app.route('/submit_demand', methods=['GET', 'POST'])
def submit_demand():
    """发布新需求"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    try:
        if request.method == 'POST':
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            demand_type = request.form.get('type', 'service')
            points_required = request.form.get('points', '100')
            contact_info = request.form.get('contact', '').strip()
            
            # 验证表单数据
            if not title or not description:
                flash('标题和描述不能为空', 'danger')
                return redirect(url_for('submit_demand'))
            
            try:
                points_required = int(points_required)
            except ValueError:
                points_required = 100
                
            if points_required < 10:
                flash('积分要求不能低于10分', 'danger')
                return redirect(url_for('submit_demand'))
                
            # 创建新需求
            new_demand = Demand(
                title=title,
                description=description,
                demand_type=demand_type,
                points_required=points_required,
                user_id=session['user_id'],
                contact_info=contact_info
            )
            
            db.session.add(new_demand)
            db.session.commit()
            
            flash('需求已成功发布', 'success')
            return redirect(url_for('demand_list'))
        
        return render_template('submit_demand.html')
    
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"发布需求错误: {str(e)}")
        flash('发布需求时出错，请重试', 'danger')
        return redirect(url_for('submit_demand'))

# 在 app.py 中添加后端路由
@app.route('/add_community_post', methods=['POST'])
def add_community_post():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': '请先登录'}), 401
    
    content = request.form.get('content', '').strip()
    if not content:
        return jsonify({'success': False, 'error': '内容不能为空'}), 400
    
    try:
        # 创建社区动态
        new_post = CommunityPost(
            content=content,
            user_id=session['user_id']
        )
        db.session.add(new_post)
        
        # 检查内容中是否包含"需求"或"求购"，如果包含则创建需求
        if "需求" in content or "求购" in content:
            # 创建需求
            new_demand = Demand(
                title=f"来自社区的需求-{datetime.utcnow().strftime('%H%M%S')}",
                description=content,
                demand_type='service',  # 默认服务类型
                points_required=100,   # 默认100积分
                user_id=session['user_id'],
                contact_info=User.query.get(session['user_id']).username  # 暂时用用户名作为联系方式
            )
            db.session.add(new_demand)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'username': session['username'],
            'content': content,
            'created_at': '刚刚'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# 在 app.py 中添加临时路由
@app.route('/guide')
def guide():
    return render_template('guide.html')  # 需要创建模板

@app.route('/points_rules')
def points_rules():
    return "积分规则页面"

@app.route('/faq')
def faq():
    return "常见问题页面"

@app.route('/contact')
def contact():
    return "联系我们页面"

if __name__ == '__main__':
    app.run(debug=True, port=5001)