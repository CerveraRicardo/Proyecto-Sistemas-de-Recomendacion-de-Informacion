"""
Motor de Recomendaciones Optimizado para Arquitectura Persistente
Adaptado para cálculos batch y almacenamiento en BD
Mantiene compatibilidad con uso directo desde plugin PHP
"""

import pymysql
import numpy as np
import re
from datetime import datetime
from collections import defaultdict
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import html
import json

class OJSRecommendationEngine:
    """
    Motor de recomendaciones optimizado para OJS 3.3+ con almacenamiento persistente
    """
    
    def __init__(self, connection):
        self.connection = connection
        self.articles_data = {}
        self.tfidf_vectorizer = None
        self.tfidf_matrix = None
        self.similarity_matrix = None
        self.article_ids = []
        
    def load_articles_data(self):
        """Cargar datos de artículos desde publications - Optimizado para batch"""
        print("📚 Cargando datos de artículos para procesamiento batch...")
        
        with self.connection.cursor() as cursor:
            # Query optimizado para cargar todos los artículos de una vez
            cursor.execute("""
                SELECT 
                    p.publication_id,
                    p.submission_id,
                    s.context_id,
                    p.date_published,
                    p.status,
                    
                    -- Títulos priorizando español
                    COALESCE(
                        ps_title_es.setting_value,
                        ps_title_en.setting_value,
                        'Sin título'
                    ) as title,
                    
                    -- Abstracts priorizando español
                    COALESCE(
                        ps_abstract_es.setting_value,
                        ps_abstract_en.setting_value,
                        ''
                    ) as abstract,
                    
                    -- Autores con nombres completos
                    GROUP_CONCAT(
                        DISTINCT COALESCE(
                            CONCAT(
                                COALESCE(aus_fname.setting_value, ''), 
                                ' ', 
                                COALESCE(aus_lname.setting_value, '')
                            ),
                            a.email,
                            'Autor desconocido'
                        ) 
                        SEPARATOR '; '
                    ) as authors,
                    
                    -- Afiliaciones de autores
                    GROUP_CONCAT(
                        DISTINCT aus_affiliation.setting_value
                        SEPARATOR '; '
                    ) as affiliations
                    
                FROM publications p
                JOIN submissions s ON p.submission_id = s.submission_id
                
                -- Títulos
                LEFT JOIN publication_settings ps_title_es ON p.publication_id = ps_title_es.publication_id 
                    AND ps_title_es.setting_name = 'title' AND ps_title_es.locale = 'es'
                LEFT JOIN publication_settings ps_title_en ON p.publication_id = ps_title_en.publication_id 
                    AND ps_title_en.setting_name = 'title' AND ps_title_en.locale = 'en'
                
                -- Abstracts
                LEFT JOIN publication_settings ps_abstract_es ON p.publication_id = ps_abstract_es.publication_id 
                    AND ps_abstract_es.setting_name = 'abstract' AND ps_abstract_es.locale = 'es'
                LEFT JOIN publication_settings ps_abstract_en ON p.publication_id = ps_abstract_en.publication_id 
                    AND ps_abstract_en.setting_name = 'abstract' AND ps_abstract_en.locale = 'en'
                
                -- Autores
                LEFT JOIN authors a ON p.publication_id = a.publication_id
                LEFT JOIN author_settings aus_fname ON a.author_id = aus_fname.author_id 
                    AND aus_fname.setting_name = 'givenName'
                LEFT JOIN author_settings aus_lname ON a.author_id = aus_lname.author_id 
                    AND aus_lname.setting_name = 'familyName'
                LEFT JOIN author_settings aus_affiliation ON a.author_id = aus_affiliation.author_id 
                    AND aus_affiliation.setting_name = 'affiliation'
                
                WHERE p.status = 3  -- Solo publicaciones activas
                
                GROUP BY p.publication_id, p.submission_id, s.context_id, p.date_published, p.status
                HAVING title != 'Sin título'  -- Solo artículos con título
                ORDER BY p.date_published DESC
            """)
            
            articles = cursor.fetchall()
            
            for article in articles:
                # Limpiar título y abstract de HTML
                clean_title = self._clean_html_text(article['title'] or 'Sin título')
                clean_abstract = self._clean_html_text(article['abstract'] or '')
                clean_authors = self._clean_authors(article['authors'] or '')
                
                self.articles_data[article['publication_id']] = {
                    'publication_id': article['publication_id'],
                    'submission_id': article['submission_id'],
                    'title': clean_title,
                    'abstract': clean_abstract,
                    'authors': clean_authors,
                    'affiliations': article['affiliations'] or '',
                    'date_published': article['date_published'],
                    'content': self._prepare_content_for_analysis(
                        clean_title, 
                        clean_abstract, 
                        clean_authors,
                        article['affiliations'] or ''
                    )
                }
            
            print(f"✅ Cargados {len(self.articles_data)} artículos únicos")
            return len(self.articles_data)
    
    def build_similarity_matrix(self):
        """Construir matriz de similitud TF-IDF optimizada para batch processing"""
        print("🔍 Calculando similitudes entre artículos (batch processing)...")
        
        if not self.articles_data:
            self.load_articles_data()
        
        if len(self.articles_data) < 2:
            print("⚠️ Necesitas al menos 2 artículos para calcular similitudes")
            return False
        
        # Extraer contenido y preparar para vectorización
        article_contents = []
        self.article_ids = []
        
        for pub_id, article in self.articles_data.items():
            article_contents.append(article['content'])
            self.article_ids.append(pub_id)
        
        # Crear vectorizador TF-IDF optimizado para procesamiento batch
        self.tfidf_vectorizer = TfidfVectorizer(
            max_features=3000,  # Incrementado para mejor precisión en batch
            stop_words=self._get_stopwords(),
            ngram_range=(1, 3),  # Unigrams, bigrams, trigrams
            min_df=2,  # Mínimo 2 documentos para reducir ruido
            max_df=0.85,  # Máximo 85% para filtrar términos muy comunes
            analyzer='word',
            lowercase=True,
            token_pattern=r'\b[a-záéíóúñü]{2,}\b',  # Solo palabras válidas
            dtype=np.float32  # Optimización de memoria
        )
        
        try:
            # Crear matriz TF-IDF
            print("   🔢 Generando matriz TF-IDF...")
            self.tfidf_matrix = self.tfidf_vectorizer.fit_transform(article_contents)
            
            # Calcular similitud coseno con optimización de memoria
            print("   📊 Calculando similitudes coseno...")
            self.similarity_matrix = cosine_similarity(self.tfidf_matrix, dense_output=True)
            
            print(f"✅ Matriz de similitud creada: {self.similarity_matrix.shape}")
            print(f"📊 Vocabulario TF-IDF: {len(self.tfidf_vectorizer.vocabulary_)} términos")
            print(f"💾 Memoria matriz: {self.similarity_matrix.nbytes / 1024 / 1024:.1f} MB")
            
            return True
            
        except Exception as e:
            print(f"❌ Error construyendo matriz de similitud: {e}")
            return False
    
    def get_similar_articles(self, publication_id, n_recommendations=5):
        """Obtener artículos similares - Optimizado para almacenamiento persistente"""
        if self.similarity_matrix is None:
            if not self.build_similarity_matrix():
                return []
        
        if publication_id not in self.articles_data:
            return []
        
        try:
            # Obtener índice del artículo
            article_index = self.article_ids.index(publication_id)
        except ValueError:
            return []
        
        # Obtener similitudes
        similarities = self.similarity_matrix[article_index]
        
        # Crear lista de recomendaciones con metadatos para persistencia
        recommendations = []
        for i, similarity_score in enumerate(similarities):
            if i != article_index and similarity_score > 0.01:  # Umbral mínimo
                other_pub_id = self.article_ids[i]
                article = self.articles_data[other_pub_id]
                
                recommendations.append({
                    'publication_id': other_pub_id,
                    'submission_id': article['submission_id'],
                    'title': article['title'],
                    'abstract': article['abstract'][:300] + '...' if len(article['abstract']) > 300 else article['abstract'],
                    'authors': article['authors'],
                    'date_published': article['date_published'].isoformat() if hasattr(article['date_published'], 'isoformat') else str(article['date_published']) if article['date_published'] else None,
                    'similarity_score': float(similarity_score),
                    'algorithm': 'content_based_tfidf',
                    'score': float(similarity_score),
                    'confidence': min(similarity_score * 1.5, 1.0),  # Confianza ajustada
                    'url': f'/article/view/{article["submission_id"]}',
                    # Metadatos adicionales para persistencia
                    'calculation_timestamp': datetime.now().isoformat(),
                    'tfidf_features': len(self.tfidf_vectorizer.vocabulary_),
                    'total_articles_compared': len(self.articles_data)
                })
        
        # Ordenar por similitud descendente
        recommendations.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        # Si no hay suficientes similares con umbral alto, usar umbral más bajo
        if len(recommendations) < n_recommendations:
            additional_recs = []
            for i, similarity_score in enumerate(similarities):
                if (i != article_index and 
                    similarity_score > 0.005 and  # Umbral muy bajo
                    not any(r['publication_id'] == self.article_ids[i] for r in recommendations)):
                    
                    other_pub_id = self.article_ids[i]
                    article = self.articles_data[other_pub_id]
                    
                    additional_recs.append({
                        'publication_id': other_pub_id,
                        'submission_id': article['submission_id'],
                        'title': article['title'],
                        'abstract': article['abstract'][:300] + '...' if len(article['abstract']) > 300 else article['abstract'],
                        'authors': article['authors'],
                        'date_published': article['date_published'].isoformat() if hasattr(article['date_published'], 'isoformat') else str(article['date_published']) if article['date_published'] else None,
                        'similarity_score': float(similarity_score),
                        'algorithm': 'content_based_tfidf_fallback',
                        'score': float(similarity_score),
                        'confidence': min(similarity_score * 1.2, 0.7),  # Menor confianza para fallback
                        'url': f'/article/view/{article["submission_id"]}',
                        'calculation_timestamp': datetime.now().isoformat(),
                        'tfidf_features': len(self.tfidf_vectorizer.vocabulary_),
                        'total_articles_compared': len(self.articles_data)
                    })
            
            # Ordenar adicionales y agregar los necesarios
            additional_recs.sort(key=lambda x: x['similarity_score'], reverse=True)
            needed = n_recommendations - len(recommendations)
            recommendations.extend(additional_recs[:needed])
        
        return recommendations[:n_recommendations]
    
    def get_all_similarities_batch(self, min_similarity=0.01):
        """
        Obtener todas las similitudes para almacenamiento batch
        Nuevo método optimizado para la arquitectura persistente
        """
        if self.similarity_matrix is None:
            if not self.build_similarity_matrix():
                return {}
        
        print("🔄 Generando similitudes batch para almacenamiento persistente...")
        
        all_similarities = {}
        total_pairs = 0
        
        for i, source_id in enumerate(self.article_ids):
            similarities = self.similarity_matrix[i]
            article_similarities = []
            
            for j, similarity_score in enumerate(similarities):
                if i != j and similarity_score >= min_similarity:
                    target_id = self.article_ids[j]
                    target_article = self.articles_data[target_id]
                    
                    article_similarities.append({
                        'target_publication_id': target_id,
                        'target_submission_id': target_article['submission_id'],
                        'similarity_score': float(similarity_score),
                        'target_title': target_article['title'],
                        'target_authors': target_article['authors'],
                        'target_abstract_preview': target_article['abstract'][:200] if target_article['abstract'] else '',
                        'algorithm': 'batch_tfidf_cosine',
                        'confidence': min(similarity_score * 1.5, 1.0)
                    })
                    total_pairs += 1
            
            # Ordenar por similitud descendente
            article_similarities.sort(key=lambda x: x['similarity_score'], reverse=True)
            all_similarities[source_id] = article_similarities
            
            # Log progreso cada 100 artículos
            if (i + 1) % 100 == 0:
                print(f"   Procesados {i + 1}/{len(self.article_ids)} artículos...")
        
        print(f"✅ Batch similitudes generado: {total_pairs} pares de similitud")
        return all_similarities
    
    def get_recommendations_by_author_similarity(self, target_authors, n_recommendations=5):
        """Recomendaciones basadas en autores similares - Optimizado"""
        if not self.articles_data:
            self.load_articles_data()
        
        target_authors = target_authors.lower()
        recommendations = []
        
        for pub_id, article in self.articles_data.items():
            authors = article['authors'].lower()
            
            # Calcular similitud de autores con algoritmo mejorado
            similarity = self._calculate_author_similarity(target_authors, authors)
            
            if similarity > 0.3:
                recommendations.append({
                    'publication_id': pub_id,
                    'submission_id': article['submission_id'],
                    'title': article['title'],
                    'abstract': article['abstract'][:300] + '...' if len(article['abstract']) > 300 else article['abstract'],
                    'authors': article['authors'],
                    'date_published': article['date_published'].isoformat() if hasattr(article['date_published'], 'isoformat') else str(article['date_published']) if article['date_published'] else None,
                    'similarity_score': similarity,
                    'algorithm': 'author_similarity_enhanced',
                    'score': similarity,
                    'confidence': similarity,
                    'url': f'/article/view/{article["submission_id"]}',
                    'recommendation_reason': f'Autor similar ({similarity:.1%} coincidencia)'
                })
        
        recommendations.sort(key=lambda x: x['similarity_score'], reverse=True)
        return recommendations[:n_recommendations]
    
    def get_recent_articles(self, n_recommendations=10):
        """Obtener artículos más recientes - Optimizado para persistencia"""
        if not self.articles_data:
            self.load_articles_data()
        
        articles_list = []
        current_time = datetime.now()
        
        for pub_id, article in self.articles_data.items():
            # Calcular score basado en recencia con decay mejorado
            if article['date_published']:
                # Convertir date a datetime si es necesario
                if hasattr(article['date_published'], 'date'):
                    pub_date = article['date_published']
                else:
                    from datetime import time
                    pub_date = datetime.combine(article['date_published'], time())
                
                days_ago = (current_time - pub_date).days
                
                # Función de decay más suave
                if days_ago <= 7:
                    recency_score = 1.0
                elif days_ago <= 30:
                    recency_score = 0.9 - (days_ago - 7) * 0.02  # Decay gradual
                elif days_ago <= 90:
                    recency_score = 0.7 - (days_ago - 30) * 0.008
                else:
                    recency_score = max(0.1, 0.5 - (days_ago - 90) * 0.001)
                    
            else:
                recency_score = 0.3  # Score por defecto para artículos sin fecha
            
            articles_list.append({
                'publication_id': pub_id,
                'submission_id': article['submission_id'],
                'title': article['title'],
                'abstract': article['abstract'][:300] + '...' if len(article['abstract']) > 300 else article['abstract'],
                'authors': article['authors'],
                'date_published': article['date_published'].isoformat() if hasattr(article['date_published'], 'isoformat') else str(article['date_published']) if article['date_published'] else None,
                'predicted_rating': recency_score,
                'algorithm': 'recency_based_enhanced',
                'score': recency_score,
                'confidence': 0.8,
                'url': f'/article/view/{article["submission_id"]}',
                'days_since_published': days_ago if article['date_published'] else None,
                'recency_category': self._get_recency_category(days_ago if article['date_published'] else 999)
            })
        
        articles_list.sort(key=lambda x: x['predicted_rating'], reverse=True)
        return articles_list[:n_recommendations]
    
    # ================================
    # MÉTODOS AUXILIARES OPTIMIZADOS
    # ================================
    
    def _calculate_author_similarity(self, target_authors, article_authors):
        """Calcular similitud de autores con algoritmo mejorado"""
        if not target_authors or not article_authors:
            return 0.0
        
        target_names = set(self._extract_author_names(target_authors))
        article_names = set(self._extract_author_names(article_authors))
        
        if not target_names or not article_names:
            return 0.0
        
        # Coincidencias exactas
        exact_matches = target_names.intersection(article_names)
        if exact_matches:
            return min(1.0, len(exact_matches) / min(len(target_names), len(article_names)))
        
        # Coincidencias parciales (apellidos)
        target_surnames = {name.split()[-1] for name in target_names if ' ' in name}
        article_surnames = {name.split()[-1] for name in article_names if ' ' in name}
        
        surname_matches = target_surnames.intersection(article_surnames)
        if surname_matches:
            return min(0.7, len(surname_matches) / min(len(target_surnames), len(article_surnames)) * 0.7)
        
        return 0.0
    
    def _extract_author_names(self, authors_string):
        """Extraer nombres individuales de autores"""
        if not authors_string:
            return []
        
        # Separar por ; y limpiar
        names = []
        for author in authors_string.split(';'):
            author = author.strip()
            if author and author not in ['Autor desconocido', '']:
                # Limpiar y normalizar
                author = re.sub(r'\s+', ' ', author).strip()
                if len(author) > 2:
                    names.append(author)
        
        return names
    
    def _get_recency_category(self, days_ago):
        """Categorizar artículos por recencia"""
        if days_ago <= 7:
            return 'very_recent'
        elif days_ago <= 30:
            return 'recent'
        elif days_ago <= 90:
            return 'moderately_recent'
        else:
            return 'older'
    
    def _clean_html_text(self, text):
        """Limpiar texto HTML - Optimizado"""
        if not text:
            return ''
        
        # Decodificar entidades HTML
        text = html.unescape(text)
        
        # Remover tags HTML
        text = re.sub(r'<[^>]+>', ' ', text)
        
        # Limpiar espacios extra y caracteres especiales
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^\w\sáéíóúñüÁÉÍÓÚÑÜ.,;:()\-]', ' ', text)
        
        return text.strip()
    
    def _clean_authors(self, authors_text):
        """Limpiar y formatear nombres de autores - Optimizado"""
        if not authors_text:
            return ''
        
        # Separar autores y limpiar nombres
        authors = []
        for author in authors_text.split(';'):
            author = author.strip()
            if author and author not in ['Autor desconocido', '']:
                # Remover duplicados y espacios extra
                author = re.sub(r'\s+', ' ', author).strip()
                # Validar que no sea solo espacios o caracteres especiales
                if len(author) > 2 and author not in authors:
                    authors.append(author)
        
        return '; '.join(authors)
    
    def _prepare_content_for_analysis(self, title, abstract, authors, affiliations):
        """Preparar contenido para análisis TF-IDF - Optimizado para batch"""
        content_parts = []
        
        # Título (peso triple) - Más importante para similitud
        if title and title != 'Sin título':
            content_parts.extend([title] * 3)
        
        # Abstract (peso doble)
        if abstract:
            # Dividir abstract en oraciones para mejor granularidad
            sentences = re.split(r'[.!?]+', abstract)
            for sentence in sentences:
                if len(sentence.strip()) > 10:  # Solo oraciones significativas
                    content_parts.extend([sentence.strip()] * 2)
        
        # Autores (peso simple pero importante para clustering)
        if authors:
            content_parts.append(authors)
        
        # Afiliaciones (peso menor)
        if affiliations:
            content_parts.append(affiliations)
        
        # Combinar y limpiar para TF-IDF
        full_content = ' '.join(content_parts)
        
        # Normalización más agresiva para TF-IDF
        full_content = re.sub(r'[^\w\sáéíóúñüÁÉÍÓÚÑÜ]', ' ', full_content.lower())
        full_content = re.sub(r'\b\w{1,2}\b', ' ', full_content)  # Remover palabras muy cortas
        full_content = re.sub(r'\s+', ' ', full_content).strip()
        
        return full_content
    
    def _get_stopwords(self):
        """Stopwords optimizadas para contenido académico en español e inglés"""
        return [
            # Español básico
            'el', 'la', 'de', 'que', 'y', 'a', 'en', 'un', 'es', 'se', 'no', 'te', 'lo', 'le',
            'su', 'por', 'son', 'con', 'para', 'como', 'las', 'del', 'los', 'una', 'al', 'pero',
            'sus', 'ya', 'o', 'fue', 'este', 'ha', 'si', 'porque', 'esta', 'entre', 'cuando',
            'muy', 'sin', 'sobre', 'también', 'me', 'hasta', 'hay', 'donde', 'quien', 'desde',
            'todos', 'durante', 'antes', 'después', 'más', 'menos', 'otro', 'otra', 'otros',
            
            # Inglés básico
            'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
            'an', 'be', 'this', 'that', 'are', 'was', 'were', 'been', 'have', 'has', 'had',
            'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must',
            
            # Términos académicos comunes (que no aportan diferenciación)
            'research', 'study', 'analysis', 'method', 'results', 'conclusion', 'abstract',
            'investigación', 'estudio', 'análisis', 'método', 'resultados', 'conclusión',
            'revista', 'journal', 'article', 'paper', 'artículo', 'trabajo', 'presenta',
            'presenta', 'propone', 'desarrolla', 'establece', 'mediante', 'través',
            
            # Conectores y preposiciones adicionales
            'hacia', 'bajo', 'según', 'mientras', 'aunque', 'sino', 'cada', 'tanto',
            'through', 'during', 'before', 'after', 'above', 'below', 'between', 'among',
            
            # Términos de estructura académica
            'introducción', 'introduction', 'metodología', 'methodology', 'discusión',
            'discussion', 'referencias', 'references', 'conclusiones', 'conclusions'
        ]
    
    # ================================
    # MÉTODOS DE UTILIDAD PARA PERSISTENCIA
    # ================================
    
    def get_articles_summary(self):
        """Obtener resumen de artículos cargados"""
        if not self.articles_data:
            return {}
        
        total_articles = len(self.articles_data)
        articles_with_abstract = sum(1 for a in self.articles_data.values() if a['abstract'])
        articles_with_authors = sum(1 for a in self.articles_data.values() if a['authors'])
        
        # Calcular distribución por año
        year_distribution = defaultdict(int)
        for article in self.articles_data.values():
            if article['date_published']:
                year = article['date_published'].year if hasattr(article['date_published'], 'year') else datetime.now().year
                year_distribution[year] += 1
        
        return {
            'total_articles': total_articles,
            'articles_with_abstract': articles_with_abstract,
            'articles_with_authors': articles_with_authors,
            'abstract_coverage': articles_with_abstract / total_articles if total_articles > 0 else 0,
            'author_coverage': articles_with_authors / total_articles if total_articles > 0 else 0,
            'year_distribution': dict(year_distribution),
            'vocabulary_size': len(self.tfidf_vectorizer.vocabulary_) if self.tfidf_vectorizer else 0,
            'similarity_matrix_shape': self.similarity_matrix.shape if self.similarity_matrix is not None else None
        }
    
    def validate_similarity_matrix(self):
        """Validar integridad de la matriz de similitud"""
        if self.similarity_matrix is None:
            return {'valid': False, 'error': 'Matriz no inicializada'}
        
        try:
            # Verificar que es simétrica
            is_symmetric = np.allclose(self.similarity_matrix, self.similarity_matrix.T, rtol=1e-10)
            
            # Verificar diagonal = 1
            diagonal_ones = np.allclose(np.diag(self.similarity_matrix), 1.0, rtol=1e-10)
            
            # Verificar rango [0,1]
            values_in_range = (self.similarity_matrix >= 0).all() and (self.similarity_matrix <= 1).all()
            
            # Estadísticas básicas
            stats = {
                'mean_similarity': float(np.mean(self.similarity_matrix)),
                'std_similarity': float(np.std(self.similarity_matrix)),
                'max_similarity': float(np.max(self.similarity_matrix[self.similarity_matrix < 1.0])),
                'min_similarity': float(np.min(self.similarity_matrix))
            }
            
            return {
                'valid': is_symmetric and diagonal_ones and values_in_range,
                'is_symmetric': is_symmetric,
                'diagonal_ones': diagonal_ones,
                'values_in_range': values_in_range,
                'statistics': stats,
                'shape': self.similarity_matrix.shape
            }
            
        except Exception as e:
            return {'valid': False, 'error': str(e)}

# ================================
# FUNCIONES DE API COMPATIBLES CON PLUGIN PHP
# ================================

def get_recommendations_for_article(connection, publication_id, n_recommendations=5):
    """Obtener recomendaciones para un artículo específico - Compatible con plugin PHP"""
    try:
        engine = OJSRecommendationEngine(connection)
        return engine.get_similar_articles(publication_id, n_recommendations)
    except Exception as e:
        print(f"❌ Error: {e}")
        return []

def get_recommendations_for_user(connection, user_id=None, n_recommendations=10):
    """Obtener recomendaciones para un usuario - Compatible con plugin PHP"""
    try:
        engine = OJSRecommendationEngine(connection)
        # Por ahora, devolver artículos recientes
        # TODO: Implementar basado en historial de usuario cuando haya tracking
        return engine.get_recent_articles(n_recommendations)
    except Exception as e:
        print(f"❌ Error: {e}")
        return []

def get_recommendations_by_author(connection, author_name, n_recommendations=5):
    """Obtener recomendaciones basadas en autor - Compatible con plugin PHP"""
    try:
        engine = OJSRecommendationEngine(connection)
        return engine.get_recommendations_by_author_similarity(author_name, n_recommendations)
    except Exception as e:
        print(f"❌ Error: {e}")
        return []

def get_batch_similarities(connection, min_similarity=0.01):
    """
    Función nueva para obtener todas las similitudes en batch
    Específica para la arquitectura persistente
    """
    try:
        engine = OJSRecommendationEngine(connection)
        engine.load_articles_data()
        
        if not engine.build_similarity_matrix():
            return {}
        
        return engine.get_all_similarities_batch(min_similarity)
    except Exception as e:
        print(f"❌ Error en batch similarities: {e}")
        return {}

def validate_system_health(connection):
    """
    Validar salud del sistema de recomendaciones
    Útil para monitoring y debugging
    """
    try:
        engine = OJSRecommendationEngine(connection)
        
        # Cargar datos
        articles_count = engine.load_articles_data()
        
        if articles_count < 2:
            return {
                'healthy': False,
                'error': 'Insuficientes artículos para recomendaciones',
                'articles_count': articles_count
            }
        
        # Construir matriz
        matrix_success = engine.build_similarity_matrix()
        
        if not matrix_success:
            return {
                'healthy': False,
                'error': 'Error construyendo matriz de similitud',
                'articles_count': articles_count
            }
        
        # Validar matriz
        validation = engine.validate_similarity_matrix()
        summary = engine.get_articles_summary()
        
        return {
            'healthy': validation['valid'],
            'articles_summary': summary,
            'matrix_validation': validation,
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        return {
            'healthy': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }

# ================================
# EJEMPLO DE USO
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
        print("🚀 PROBANDO MOTOR DE RECOMENDACIONES OPTIMIZADO")
        print("=" * 70)
        
        # Validar salud del sistema
        health = validate_system_health(connection)
        
        if health['healthy']:
            print("✅ Sistema saludable")
            print(f"📊 Artículos cargados: {health['articles_summary']['total_articles']}")
            print(f"📈 Vocabulario TF-IDF: {health['articles_summary']['vocabulary_size']}")
            print(f"🎯 Matriz similitud: {health['articles_summary']['similarity_matrix_shape']}")
            
            # Probar recomendaciones
            engine = OJSRecommendationEngine(connection)
            engine.load_articles_data()
            engine.build_similarity_matrix()
            
            if engine.articles_data:
                first_pub_id = list(engine.articles_data.keys())[0]
                first_article = engine.articles_data[first_pub_id]
                
                print(f"\n🔍 ARTÍCULO BASE:")
                print(f"   ID: {first_pub_id}")
                print(f"   Título: {first_article['title']}")
                print(f"   Autores: {first_article['authors']}")
                
                print(f"\n📋 ARTÍCULOS SIMILARES:")
                similar = engine.get_similar_articles(first_pub_id, 3)
                
                for i, rec in enumerate(similar, 1):
                    print(f"{i}. {rec['title']}")
                    print(f"   Similitud: {rec['similarity_score']:.3f}")
                    print(f"   Algoritmo: {rec['algorithm']}")
                    print(f"   Confianza: {rec['confidence']:.3f}")
                    print()
                
                # Probar batch similarities
                print("🔄 Probando batch similarities...")
                batch_similarities = engine.get_all_similarities_batch(min_similarity=0.05)
                total_similarities = sum(len(sims) for sims in batch_similarities.values())
                print(f"✅ Batch generado: {total_similarities} similitudes")
        else:
            print(f"❌ Sistema no saludable: {health['error']}")
        
        print("\n✅ ¡Motor optimizado funcionando correctamente!")
        
    finally:
        connection.close()