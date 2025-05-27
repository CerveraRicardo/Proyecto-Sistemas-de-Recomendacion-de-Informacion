"""
Sistema de Recomendaciones Híbrido Completo
Incluye predicción de comportamiento, ratings implícitos y modelo híbrido
"""

import pymysql
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.decomposition import TruncatedSVD
from sklearn.cluster import KMeans
import math
import re
import html

class HybridRecommendationSystem:
    """
    Sistema híbrido que combina:
    1. Content-Based Filtering
    2. Collaborative Filtering
    3. Predicción de ratings implícitos
    4. Análisis de comportamiento
    5. Clustering de usuarios
    """
    
    def __init__(self, connection):
        self.connection = connection
        self.articles_data = {}
        self.user_behavior_data = {}
        self.user_item_matrix = None
        self.content_similarity_matrix = None
        self.user_profiles = {}
        self.article_popularity = {}
        
        # Modelos ML
        self.tfidf_vectorizer = None
        self.svd_model = None
        self.user_clusters = None
        
    def load_comprehensive_data(self):
        """Cargar todos los datos necesarios para el modelo híbrido"""
        print("📚 Cargando datos comprehensivos...")
        
        # 1. Cargar artículos
        self._load_articles_data()
        
        # 2. Cargar comportamiento de usuarios
        self._load_user_behavior()
        
        # 3. Cargar perfiles de usuarios
        self._load_user_profiles()
        
        # 4. Calcular popularidad de artículos
        self._calculate_article_popularity()
        
        print(f"✅ Datos cargados: {len(self.articles_data)} artículos, {len(self.user_behavior_data)} usuarios")
    
    def _load_articles_data(self):
        """Cargar artículos con metadatos completos"""
        with self.connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    p.publication_id,
                    p.submission_id,
                    s.context_id,
                    p.date_published,
                    p.status,
                    
                    COALESCE(ps_title_es.setting_value, ps_title_en.setting_value, 'Sin título') as title,
                    COALESCE(ps_abstract_es.setting_value, ps_abstract_en.setting_value, '') as abstract,
                    
                    GROUP_CONCAT(DISTINCT CONCAT(
                        COALESCE(aus_fname.setting_value, ''), ' ', 
                        COALESCE(aus_lname.setting_value, '')
                    ) SEPARATOR '; ') as authors,
                    
                    GROUP_CONCAT(DISTINCT aus_affiliation.setting_value SEPARATOR '; ') as affiliations,
                    
                    -- Categorías si existen
                    GROUP_CONCAT(DISTINCT pc.category_id) as category_ids
                    
                FROM publications p
                JOIN submissions s ON p.submission_id = s.submission_id
                
                LEFT JOIN publication_settings ps_title_es ON p.publication_id = ps_title_es.publication_id 
                    AND ps_title_es.setting_name = 'title' AND ps_title_es.locale = 'es'
                LEFT JOIN publication_settings ps_title_en ON p.publication_id = ps_title_en.publication_id 
                    AND ps_title_en.setting_name = 'title' AND ps_title_en.locale = 'en'
                LEFT JOIN publication_settings ps_abstract_es ON p.publication_id = ps_abstract_es.publication_id 
                    AND ps_abstract_es.setting_name = 'abstract' AND ps_abstract_es.locale = 'es'
                LEFT JOIN publication_settings ps_abstract_en ON p.publication_id = ps_abstract_en.publication_id 
                    AND ps_abstract_en.setting_name = 'abstract' AND ps_abstract_en.locale = 'en'
                
                LEFT JOIN authors a ON p.publication_id = a.publication_id
                LEFT JOIN author_settings aus_fname ON a.author_id = aus_fname.author_id 
                    AND aus_fname.setting_name = 'givenName'
                LEFT JOIN author_settings aus_lname ON a.author_id = aus_lname.author_id 
                    AND aus_lname.setting_name = 'familyName'
                LEFT JOIN author_settings aus_affiliation ON a.author_id = aus_affiliation.author_id 
                    AND aus_affiliation.setting_name = 'affiliation'
                
                LEFT JOIN publication_categories pc ON p.publication_id = pc.publication_id
                
                WHERE p.status = 3
                GROUP BY p.publication_id, p.submission_id, s.context_id, p.date_published, p.status
                HAVING title != 'Sin título'
                ORDER BY p.date_published DESC
            """)
            
            for article in cursor.fetchall():
                clean_title = self._clean_html_text(article['title'])
                clean_abstract = self._clean_html_text(article['abstract'])
                
                self.articles_data[article['publication_id']] = {
                    'publication_id': article['publication_id'],
                    'submission_id': article['submission_id'],
                    'title': clean_title,
                    'abstract': clean_abstract,
                    'authors': self._clean_authors(article['authors'] or ''),
                    'affiliations': article['affiliations'] or '',
                    'category_ids': article['category_ids'] or '',
                    'date_published': article['date_published'],
                    'days_since_published': self._calculate_days_since_published(article['date_published']),
                    'content_vector': None,  # Se calculará después
                }
    
    def _load_user_behavior(self):
        """Cargar y analizar comportamiento de usuarios"""
        with self.connection.cursor() as cursor:
            # Crear comportamiento sintético basado en sesiones y datos disponibles
            cursor.execute("""
                SELECT 
                    u.user_id,
                    u.username,
                    u.date_registered,
                    u.date_last_login,
                    COUNT(DISTINCT s.session_id) as session_count,
                    MAX(s.last_used) as last_activity
                FROM users u
                LEFT JOIN sessions s ON u.user_id = s.user_id
                GROUP BY u.user_id, u.username, u.date_registered, u.date_last_login
            """)
            
            users = cursor.fetchall()
            
            for user in users:
                user_id = user['user_id']
                
                # Generar comportamiento sintético basado en patrones reales
                self.user_behavior_data[user_id] = {
                    'user_id': user_id,
                    'username': user['username'],
                    'registration_days': self._calculate_days_since_registration(user['date_registered']),
                    'last_login_days': self._calculate_days_since_last_login(user['date_last_login']),
                    'session_count': user['session_count'] or 0,
                    'activity_level': self._calculate_activity_level(user),
                    'article_interactions': self._generate_synthetic_interactions(user_id),
                    'predicted_interests': [],  # Se calculará con clustering
                    'user_type': self._classify_user_type(user)
                }
    
    def _load_user_profiles(self):
        """Cargar perfiles detallados de usuarios"""
        with self.connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    u.user_id,
                    u.username,
                    u.email,
                    fname.setting_value as first_name,
                    lname.setting_value as last_name,
                    country.setting_value as country,
                    affiliation.setting_value as affiliation,
                    bio.setting_value as biography,
                    interests.setting_value as research_interests
                FROM users u
                LEFT JOIN user_settings fname ON u.user_id = fname.user_id 
                    AND fname.setting_name = 'givenName'
                LEFT JOIN user_settings lname ON u.user_id = lname.user_id 
                    AND lname.setting_name = 'familyName'
                LEFT JOIN user_settings country ON u.user_id = country.user_id 
                    AND country.setting_name = 'country'
                LEFT JOIN user_settings affiliation ON u.user_id = affiliation.user_id 
                    AND affiliation.setting_name = 'affiliation'
                LEFT JOIN user_settings bio ON u.user_id = bio.user_id 
                    AND bio.setting_name = 'biography'
                LEFT JOIN user_settings interests ON u.user_id = interests.user_id 
                    AND interests.setting_name = 'interests'
            """)
            
            for user in cursor.fetchall():
                self.user_profiles[user['user_id']] = {
                    'full_name': f"{user['first_name'] or ''} {user['last_name'] or ''}".strip(),
                    'country': user['country'] or '',
                    'affiliation': user['affiliation'] or '',
                    'biography': user['biography'] or '',
                    'research_interests': user['research_interests'] or '',
                    'profile_completeness': self._calculate_profile_completeness(user)
                }
    
    def _generate_synthetic_interactions(self, user_id):
        """Generar interacciones sintéticas basadas en patrones realistas"""
        interactions = {}
        
        # Simular que usuarios han visto algunos artículos
        # En un sistema real, esto vendría de logs de acceso
        article_ids = list(self.articles_data.keys())
        
        # Usuarios más activos ven más artículos
        behavior = self.user_behavior_data.get(user_id, {})
        activity_level = behavior.get('activity_level', 0.3)
        
        # Número de artículos que ha visto el usuario
        viewed_count = int(len(article_ids) * activity_level * np.random.uniform(0.1, 0.8))
        viewed_articles = np.random.choice(article_ids, min(viewed_count, len(article_ids)), replace=False)
        
        for article_id in viewed_articles:
            # Rating implícito basado en factores realistas
            base_rating = np.random.uniform(2.0, 4.5)
            
            # Factores que afectan el rating
            article = self.articles_data[article_id]
            
            # Artículos más recientes tienden a tener mejor rating
            recency_bonus = max(0, 1 - (article['days_since_published'] / 365)) * 0.5
            
            # Simulación de preferencias por contenido
            content_preference = np.random.uniform(-0.3, 0.7)
            
            final_rating = min(5.0, base_rating + recency_bonus + content_preference)
            
            interactions[article_id] = {
                'rating': final_rating,
                'views': np.random.randint(1, 5),
                'time_spent': np.random.uniform(30, 300),  # segundos
                'interaction_date': datetime.now() - timedelta(days=np.random.randint(1, 180))
            }
        
        return interactions
    
    def build_user_item_matrix(self):
        """Construir matriz usuario-artículo para collaborative filtering"""
        print("🔢 Construyendo matriz usuario-artículo...")
        
        users = list(self.user_behavior_data.keys())
        articles = list(self.articles_data.keys())
        
        # Crear matriz
        matrix = np.zeros((len(users), len(articles)))
        
        for i, user_id in enumerate(users):
            user_interactions = self.user_behavior_data[user_id]['article_interactions']
            for j, article_id in enumerate(articles):
                if article_id in user_interactions:
                    matrix[i, j] = user_interactions[article_id]['rating']
        
        self.user_item_matrix = matrix
        self.user_ids = users
        self.article_ids = articles
        
        print(f"✅ Matriz creada: {matrix.shape} (usuarios x artículos)")
        return matrix.shape[0] > 0 and matrix.shape[1] > 0
    
    def build_content_similarity_matrix(self):
        """Construir matriz de similitud de contenido"""
        print("📝 Construyendo matriz de similitud de contenido...")
        
        # Preparar textos para TF-IDF
        texts = []
        article_ids = []
        
        for pub_id, article in self.articles_data.items():
            text = f"{article['title']} {article['abstract']} {article['authors']}"
            text = self._clean_text_for_tfidf(text)
            texts.append(text)
            article_ids.append(pub_id)
        
        # Crear vectorizador TF-IDF
        self.tfidf_vectorizer = TfidfVectorizer(
            max_features=1000,
            stop_words=self._get_stopwords(),
            ngram_range=(1, 2),
            min_df=1,
            max_df=0.8
        )
        
        # Crear matriz TF-IDF
        tfidf_matrix = self.tfidf_vectorizer.fit_transform(texts)
        
        # Calcular similitud coseno
        self.content_similarity_matrix = cosine_similarity(tfidf_matrix)
        
        # Almacenar vectores de contenido en artículos
        for i, pub_id in enumerate(article_ids):
            self.articles_data[pub_id]['content_vector'] = tfidf_matrix[i].toarray()[0]
        
        print(f"✅ Matriz de contenido creada: {self.content_similarity_matrix.shape}")
        return True
    
    def train_collaborative_model(self):
        """Entrenar modelo de collaborative filtering con SVD"""
        print("🧠 Entrenando modelo collaborative filtering...")
        
        if self.user_item_matrix is None:
            self.build_user_item_matrix()
        
        # Solo entrenar si hay suficientes datos
        if self.user_item_matrix.shape[0] < 2 or self.user_item_matrix.shape[1] < 2:
            print("⚠️ Insuficientes datos para collaborative filtering")
            return False
        
        # Usar SVD para reducción de dimensionalidad
        self.svd_model = TruncatedSVD(n_components=min(5, min(self.user_item_matrix.shape) - 1))
        self.user_factors = self.svd_model.fit_transform(self.user_item_matrix)
        self.item_factors = self.svd_model.components_.T
        
        print(f"✅ Modelo SVD entrenado: {self.user_factors.shape[1]} factores")
        return True
    
    def cluster_users(self):
        """Clustering de usuarios basado en comportamiento"""
        print("👥 Clustering de usuarios...")
        
        if len(self.user_behavior_data) < 3:
            print("⚠️ Insuficientes usuarios para clustering")
            return False
        
        # Características para clustering
        features = []
        user_ids = []
        
        for user_id, behavior in self.user_behavior_data.items():
            feature_vector = [
                behavior['activity_level'],
                behavior['session_count'],
                behavior['registration_days'] / 365,  # Normalizar
                len(behavior['article_interactions']),
                np.mean([interaction['rating'] for interaction in behavior['article_interactions'].values()]) if behavior['article_interactions'] else 2.5
            ]
            features.append(feature_vector)
            user_ids.append(user_id)
        
        # K-means clustering
        n_clusters = min(3, len(features))  # Máximo 3 clusters
        kmeans = KMeans(n_clusters=n_clusters, random_state=42)
        cluster_labels = kmeans.fit_predict(features)
        
        # Asignar clusters a usuarios
        for i, user_id in enumerate(user_ids):
            self.user_behavior_data[user_id]['cluster'] = cluster_labels[i]
        
        self.user_clusters = kmeans
        print(f"✅ {n_clusters} clusters de usuarios creados")
        return True
    
    def predict_rating(self, user_id, article_id):
        """Predicción híbrida de rating para usuario-artículo"""
        
        # Pesos para el modelo híbrido
        content_weight = 0.4
        collaborative_weight = 0.3
        popularity_weight = 0.2
        behavioral_weight = 0.1
        
        predictions = []
        
        # 1. Predicción basada en contenido
        content_score = self._predict_content_based(user_id, article_id)
        if content_score > 0:
            predictions.append(('content', content_score, content_weight))
        
        # 2. Predicción collaborative filtering
        if self.svd_model is not None:
            collab_score = self._predict_collaborative(user_id, article_id)
            if collab_score > 0:
                predictions.append(('collaborative', collab_score, collaborative_weight))
        
        # 3. Predicción basada en popularidad
        popularity_score = self._predict_popularity_based(article_id)
        predictions.append(('popularity', popularity_score, popularity_weight))
        
        # 4. Predicción basada en comportamiento
        behavioral_score = self._predict_behavior_based(user_id, article_id)
        predictions.append(('behavioral', behavioral_score, behavioral_weight))
        
        # Combinar predicciones
        if not predictions:
            return 2.5, 0.1, ['no_data']  # Rating por defecto
        
        weighted_sum = sum(score * weight for _, score, weight in predictions)
        total_weight = sum(weight for _, score, weight in predictions)
        final_rating = weighted_sum / total_weight
        
        # Confianza basada en número de métodos usados
        confidence = min(len(predictions) / 4.0, 1.0)
        
        # Detalles de la predicción
        details = [f"{method}:{score:.2f}" for method, score, _ in predictions]
        
        return final_rating, confidence, details
    
    def _predict_content_based(self, user_id, article_id):
        """Predicción basada en similitud de contenido"""
        if user_id not in self.user_behavior_data:
            return 0
        
        user_interactions = self.user_behavior_data[user_id]['article_interactions']
        if not user_interactions:
            return 0
        
        # Encontrar artículos similares que el usuario ha visto
        article_index = self.article_ids.index(article_id) if article_id in self.article_ids else -1
        if article_index == -1:
            return 0
        
        similarities = self.content_similarity_matrix[article_index]
        weighted_ratings = []
        
        for other_article_id, interaction in user_interactions.items():
            if other_article_id in self.article_ids:
                other_index = self.article_ids.index(other_article_id)
                similarity = similarities[other_index]
                if similarity > 0.1:  # Umbral mínimo
                    weighted_ratings.append(interaction['rating'] * similarity)
        
        return np.mean(weighted_ratings) if weighted_ratings else 0
    
    def _predict_collaborative(self, user_id, article_id):
        """Predicción collaborative filtering usando SVD"""
        if user_id not in self.user_ids or article_id not in self.article_ids:
            return 0
        
        user_index = self.user_ids.index(user_id)
        article_index = self.article_ids.index(article_id)
        
        # Predicción SVD
        user_vector = self.user_factors[user_index]
        item_vector = self.item_factors[article_index]
        
        predicted_rating = np.dot(user_vector, item_vector)
        
        # Normalizar a escala 1-5
        return max(1.0, min(5.0, predicted_rating + 2.5))
    
    def _predict_popularity_based(self, article_id):
        """Predicción basada en popularidad del artículo"""
        if article_id not in self.article_popularity:
            return 2.5
        
        popularity = self.article_popularity[article_id]
        # Convertir popularidad a rating (1-5)
        return 2.0 + (popularity * 3.0)
    
    def _predict_behavior_based(self, user_id, article_id):
        """Predicción basada en patrones de comportamiento del usuario"""
        if user_id not in self.user_behavior_data:
            return 2.5
        
        user_behavior = self.user_behavior_data[user_id]
        article = self.articles_data[article_id]
        
        score = 2.5  # Base
        
        # Ajustar por nivel de actividad del usuario
        score += user_behavior['activity_level'] * 0.5
        
        # Ajustar por recencia del artículo
        if article['days_since_published'] < 30:
            score += 0.3  # Usuarios tienden a preferir artículos recientes
        
        # Ajustar por cluster de usuario (usuarios similares)
        if 'cluster' in user_behavior and self.user_clusters is not None:
            cluster_id = user_behavior['cluster']
            # Encontrar usuarios del mismo cluster que han interactuado con este artículo
            cluster_ratings = []
            for other_user_id, other_behavior in self.user_behavior_data.items():
                if (other_behavior.get('cluster') == cluster_id and 
                    article_id in other_behavior['article_interactions']):
                    cluster_ratings.append(other_behavior['article_interactions'][article_id]['rating'])
            
            if cluster_ratings:
                cluster_avg = np.mean(cluster_ratings)
                score = (score + cluster_avg) / 2  # Promedio con predicción de cluster
        
        return max(1.0, min(5.0, score))
    
    def get_hybrid_recommendations(self, user_id, n_recommendations=10):
        """Obtener recomendaciones híbridas para un usuario"""
        if user_id not in self.user_behavior_data:
            return []
        
        recommendations = []
        user_interactions = self.user_behavior_data[user_id]['article_interactions']
        
        # Evaluar todos los artículos que el usuario no ha visto
        for article_id in self.articles_data.keys():
            if article_id not in user_interactions:
                
                predicted_rating, confidence, details = self.predict_rating(user_id, article_id)
                
                if predicted_rating > 2.0:  # Umbral mínimo
                    article = self.articles_data[article_id]
                    
                    recommendations.append({
                        'publication_id': article_id,
                        'submission_id': article['submission_id'],
                        'title': article['title'],
                        'abstract': article['abstract'][:300] + '...' if len(article['abstract']) > 300 else article['abstract'],
                        'authors': article['authors'],
                        'predicted_rating': predicted_rating,
                        'confidence': confidence,
                        'algorithm': 'hybrid_model',
                        'prediction_details': details,
                        'score': predicted_rating / 5.0,  # Normalizar a 0-1
                        'date_published': article['date_published'].isoformat() if hasattr(article['date_published'], 'isoformat') else str(article['date_published']) if article['date_published'] else None,
                        'url': f'/article/view/{article["submission_id"]}'
                    })
        
        # Ordenar por rating predicho
        recommendations.sort(key=lambda x: x['predicted_rating'], reverse=True)
        return recommendations[:n_recommendations]
    
    # ================================
    # MÉTODOS AUXILIARES
    # ================================
    
    def _clean_html_text(self, text):
        """Limpiar texto HTML"""
        if not text:
            return ''
        text = html.unescape(text)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    def _clean_authors(self, authors_text):
        """Limpiar nombres de autores"""
        if not authors_text:
            return ''
        authors = []
        for author in authors_text.split(';'):
            author = author.strip()
            if author and author not in ['Autor desconocido', '']:
                author = re.sub(r'\s+', ' ', author).strip()
                if author not in authors:
                    authors.append(author)
        return '; '.join(authors)
    
    def _clean_text_for_tfidf(self, text):
        """Limpiar texto para TF-IDF"""
        text = re.sub(r'[^\w\sáéíóúñü]', ' ', text.lower())
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    def _calculate_days_since_published(self, date_published):
        """Calcular días desde publicación"""
        if not date_published:
            return 365  # Default para artículos sin fecha
        
        if hasattr(date_published, 'date'):
            pub_date = date_published
        else:
            from datetime import time
            pub_date = datetime.combine(date_published, time())
        
        return (datetime.now() - pub_date).days
    
    def _calculate_days_since_registration(self, date_registered):
        """Calcular días desde registro"""
        if not date_registered:
            return 365
        
        if hasattr(date_registered, 'date'):
            reg_date = date_registered
        else:
            from datetime import time
            reg_date = datetime.combine(date_registered, time())
        
        return (datetime.now() - reg_date).days
    
    def _calculate_days_since_last_login(self, date_last_login):
        """Calcular días desde último login"""
        if not date_last_login:
            return 30  # Default
        
        if hasattr(date_last_login, 'date'):
            login_date = date_last_login
        else:
            from datetime import time
            login_date = datetime.combine(date_last_login, time())
        
        return (datetime.now() - login_date).days
    
    def _calculate_activity_level(self, user):
        """Calcular nivel de actividad del usuario"""
        session_count = user['session_count'] or 0
        
        # Normalizar sesiones (más sesiones = más activo)
        session_score = min(session_count / 10.0, 1.0)
        
        # Factor de recencia del último login
        last_login_days = self._calculate_days_since_last_login(user['date_last_login'])
        recency_score = max(0, 1 - (last_login_days / 30))  # Decay en 30 días
        
        return (session_score + recency_score) / 2
    
    def _classify_user_type(self, user):
        """Clasificar tipo de usuario"""
        activity_level = self._calculate_activity_level(user)
        session_count = user['session_count'] or 0
        
        if activity_level > 0.7 and session_count > 5:
            return 'power_user'
        elif activity_level > 0.4:
            return 'regular_user'
        else:
            return 'casual_user'
    
    def _calculate_profile_completeness(self, user):
        """Calcular completitud del perfil"""
        fields = ['first_name', 'last_name', 'country', 'affiliation', 'biography', 'research_interests']
        completed = sum(1 for field in fields if user.get(field))
        return completed / len(fields)
    
    def _calculate_article_popularity(self):
        """Calcular popularidad de artículos"""
        popularity = defaultdict(float)
        
        # Contar interacciones por artículo
        for user_behavior in self.user_behavior_data.values():
            for article_id, interaction in user_behavior['article_interactions'].items():
                # Popularidad basada en número de vistas y rating promedio
                popularity[article_id] += interaction['views'] * (interaction['rating'] / 5.0)
        
        # Normalizar
        if popularity:
            max_pop = max(popularity.values())
            for article_id in popularity:
                popularity[article_id] /= max_pop
        
        self.article_popularity = dict(popularity)
    
    def _get_stopwords(self):
        """Stopwords para TF-IDF"""
        return [
            'el', 'la', 'de', 'que', 'y', 'a', 'en', 'un', 'es', 'se', 'no', 'te', 'lo', 'le',
            'su', 'por', 'son', 'con', 'para', 'como', 'las', 'del', 'los', 'una', 'al', 'pero',
            'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'
        ]

# ================================
# FUNCIONES DE API PARA EL SISTEMA HÍBRIDO
# ================================

def get_hybrid_recommendations_for_user(connection, user_id, n_recommendations=10):
    """Obtener recomendaciones híbridas para un usuario"""
    try:
        system = HybridRecommendationSystem(connection)
        
        # Cargar todos los datos
        system.load_comprehensive_data()
        
        # Construir modelos
        system.build_user_item_matrix()
        system.build_content_similarity_matrix()
        system.train_collaborative_model()
        system.cluster_users()
        
        # Obtener recomendaciones
        recommendations = system.get_hybrid_recommendations(user_id, n_recommendations)
        
        return recommendations
        
    except Exception as e:
        print(f"❌ Error en recomendaciones híbridas: {e}")
        return []

def predict_user_rating_for_article(connection, user_id, article_id):
    """Predecir rating que un usuario daría a un artículo específico"""
    try:
        system = HybridRecommendationSystem(connection)
        system.load_comprehensive_data()
        system.build_user_item_matrix()
        system.build_content_similarity_matrix()
        system.train_collaborative_model()
        system.cluster_users()
        
        predicted_rating, confidence, details = system.predict_rating(user_id, article_id)
        
        return {
            'user_id': user_id,
            'article_id': article_id,
            'predicted_rating': predicted_rating,
            'confidence': confidence,
            'prediction_methods': details,
            'rating_interpretation': interpret_rating(predicted_rating)
        }
        
    except Exception as e:
        print(f"❌ Error en predicción de rating: {e}")
        return None

def analyze_user_behavior(connection, user_id):
    """Analizar comportamiento detallado de un usuario"""
    try:
        system = HybridRecommendationSystem(connection)
        system.load_comprehensive_data()
        system.cluster_users()
        
        if user_id not in system.user_behavior_data:
            return None
        
        user_behavior = system.user_behavior_data[user_id]
        user_profile = system.user_profiles.get(user_id, {})
        
        # Estadísticas de interacciones
        interactions = user_behavior['article_interactions']
        interaction_stats = {
            'total_articles_viewed': len(interactions),
            'average_rating': np.mean([i['rating'] for i in interactions.values()]) if interactions else 0,
            'total_time_spent': sum([i['time_spent'] for i in interactions.values()]),
            'favorite_articles': sorted(interactions.items(), key=lambda x: x[1]['rating'], reverse=True)[:3]
        }
        
        # Predicciones de comportamiento
        behavior_predictions = {
            'likely_to_return': user_behavior['activity_level'] > 0.5,
            'engagement_level': 'High' if user_behavior['activity_level'] > 0.7 else 'Medium' if user_behavior['activity_level'] > 0.3 else 'Low',
            'predicted_next_visit_days': min(30, max(1, int(30 * (1 - user_behavior['activity_level'])))),
            'content_preference_profile': analyze_content_preferences(user_behavior, system.articles_data)
        }
        
        return {
            'user_id': user_id,
            'user_type': user_behavior['user_type'],
            'cluster': user_behavior.get('cluster', 'unknown'),
            'activity_level': user_behavior['activity_level'],
            'profile_completeness': user_profile.get('profile_completeness', 0),
            'interaction_statistics': interaction_stats,
            'behavior_predictions': behavior_predictions,
            'recommendations_quality': 'High' if len(interactions) > 5 else 'Medium' if len(interactions) > 2 else 'Low'
        }
        
    except Exception as e:
        print(f"❌ Error en análisis de comportamiento: {e}")
        return None

def get_system_insights(connection):
    """Obtener insights del sistema completo"""
    try:
        system = HybridRecommendationSystem(connection)
        system.load_comprehensive_data()
        system.build_user_item_matrix()
        system.build_content_similarity_matrix()
        system.train_collaborative_model()
        system.cluster_users()
        
        # Estadísticas generales
        total_users = len(system.user_behavior_data)
        total_articles = len(system.articles_data)
        total_interactions = sum(len(user['article_interactions']) for user in system.user_behavior_data.values())
        
        # Análisis de sparsity
        sparsity = 1 - (total_interactions / (total_users * total_articles)) if total_users * total_articles > 0 else 1
        
        # Distribución de usuarios por tipo
        user_types = defaultdict(int)
        for user in system.user_behavior_data.values():
            user_types[user['user_type']] += 1
        
        # Distribución de clusters
        clusters = defaultdict(int)
        for user in system.user_behavior_data.values():
            if 'cluster' in user:
                clusters[user['cluster']] += 1
        
        # Calidad del modelo
        model_quality = {
            'content_model_ready': system.content_similarity_matrix is not None,
            'collaborative_model_ready': system.svd_model is not None,
            'user_clustering_ready': system.user_clusters is not None,
            'sparsity_level': sparsity,
            'data_sufficiency': 'High' if sparsity < 0.95 else 'Medium' if sparsity < 0.99 else 'Low'
        }
        
        return {
            'system_overview': {
                'total_users': total_users,
                'total_articles': total_articles,
                'total_interactions': total_interactions,
                'average_interactions_per_user': total_interactions / total_users if total_users > 0 else 0
            },
            'user_distribution': dict(user_types),
            'cluster_distribution': dict(clusters),
            'model_quality': model_quality,
            'recommendation_capabilities': {
                'content_based': True,
                'collaborative_filtering': model_quality['collaborative_model_ready'],
                'hybrid_predictions': True,
                'behavior_analysis': True,
                'user_clustering': model_quality['user_clustering_ready']
            }
        }
        
    except Exception as e:
        print(f"❌ Error en insights del sistema: {e}")
        return None

# ================================
# FUNCIONES AUXILIARES
# ================================

def interpret_rating(rating):
    """Interpretar rating numérico"""
    if rating >= 4.5:
        return "Highly Recommended"
    elif rating >= 3.5:
        return "Recommended"
    elif rating >= 2.5:
        return "Neutral"
    elif rating >= 1.5:
        return "Not Recommended"
    else:
        return "Strongly Not Recommended"

def analyze_content_preferences(user_behavior, articles_data):
    """Analizar preferencias de contenido del usuario"""
    interactions = user_behavior['article_interactions']
    
    if not interactions:
        return {}
    
    # Analizar artículos con rating alto
    high_rated = {aid: interaction for aid, interaction in interactions.items() if interaction['rating'] > 3.5}
    
    if not high_rated:
        return {}
    
    # Extraer características comunes
    authors = []
    keywords = []
    
    for article_id in high_rated.keys():
        if article_id in articles_data:
            article = articles_data[article_id]
            if article['authors']:
                authors.extend(article['authors'].split(';'))
            
            # Extraer palabras clave del título
            title_words = article['title'].lower().split()
            keywords.extend([word for word in title_words if len(word) > 4])
    
    # Encontrar patrones
    from collections import Counter
    author_preferences = Counter(authors).most_common(3)
    keyword_preferences = Counter(keywords).most_common(5)
    
    return {
        'preferred_authors': [author.strip() for author, count in author_preferences],
        'preferred_topics': [keyword for keyword, count in keyword_preferences],
        'average_rating_given': np.mean([i['rating'] for i in high_rated.values()]),
        'content_engagement_level': len(high_rated) / len(interactions)
    }

# ================================
# EJEMPLO DE USO COMPLETO
# ================================

if __name__ == "__main__":
    # Conectar a la base de datos
    connection = pymysql.connect(
        host='localhost',
        user='root',
        password='',
        database='ojs_db',
        cursorclass=pymysql.cursors.DictCursor
    )
    
    try:
        print("🚀 PROBANDO SISTEMA HÍBRIDO COMPLETO")
        print("=" * 70)
        
        # Crear sistema híbrido
        system = HybridRecommendationSystem(connection)
        
        # Cargar datos completos
        system.load_comprehensive_data()
        
        if len(system.user_behavior_data) > 0 and len(system.articles_data) > 0:
            
            # Construir todos los modelos
            print("\n🔧 Construyendo modelos...")
            system.build_user_item_matrix()
            system.build_content_similarity_matrix()
            system.train_collaborative_model()
            system.cluster_users()
            
            # Probar con el primer usuario
            user_id = list(system.user_behavior_data.keys())[0]
            article_id = list(system.articles_data.keys())[0]
            
            print(f"\n👤 USUARIO DE PRUEBA: {user_id}")
            
            # 1. Predicción de rating
            print("\n🎯 PREDICCIÓN DE RATING:")
            rating, confidence, details = system.predict_rating(user_id, article_id)
            print(f"   Artículo: {system.articles_data[article_id]['title']}")
            print(f"   Rating predicho: {rating:.2f}")
            print(f"   Confianza: {confidence:.2f}")
            print(f"   Métodos usados: {', '.join(details)}")
            
            # 2. Recomendaciones híbridas
            print(f"\n📋 RECOMENDACIONES HÍBRIDAS:")
            recommendations = system.get_hybrid_recommendations(user_id, 3)
            
            for i, rec in enumerate(recommendations, 1):
                print(f"{i}. {rec['title']}")
                print(f"   Rating predicho: {rec['predicted_rating']:.2f}")
                print(f"   Confianza: {rec['confidence']:.2f}")
                print(f"   Métodos: {', '.join(rec['prediction_details'])}")
                print()
            
            # 3. Análisis de comportamiento
            print("📊 ANÁLISIS DE COMPORTAMIENTO:")
            behavior_analysis = analyze_user_behavior(connection, user_id)
            if behavior_analysis:
                print(f"   Tipo de usuario: {behavior_analysis['user_type']}")
                print(f"   Nivel de actividad: {behavior_analysis['activity_level']:.2f}")
                print(f"   Artículos vistos: {behavior_analysis['interaction_statistics']['total_articles_viewed']}")
                print(f"   Rating promedio: {behavior_analysis['interaction_statistics']['average_rating']:.2f}")
                print(f"   Nivel de engagement: {behavior_analysis['behavior_predictions']['engagement_level']}")
            
            # 4. Insights del sistema
            print("\n🔍 INSIGHTS DEL SISTEMA:")
            insights = get_system_insights(connection)
            if insights:
                print(f"   Usuarios totales: {insights['system_overview']['total_users']}")
                print(f"   Artículos totales: {insights['system_overview']['total_articles']}")
                print(f"   Interacciones totales: {insights['system_overview']['total_interactions']}")
                print(f"   Sparsity: {insights['model_quality']['sparsity_level']:.3f}")
                print(f"   Calidad de datos: {insights['model_quality']['data_sufficiency']}")
                print(f"   Modelos disponibles: {list(insights['recommendation_capabilities'].keys())}")
        
        print("\n✅ ¡Sistema híbrido completo funcionando!")
        
    finally:
        connection.close()