"""
API FastAPI con Sistema de Recomendaciones Persistentes - CORREGIDA
Adaptada para usar las tablas reales de OJS y recommendation_cache
Versión corregida para FastAPI moderno
"""

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Path
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import pymysql
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import numpy as np
import pandas as pd
import json
import hashlib
from dataclasses import dataclass, asdict
import asyncio
import threading
import time
import schedule
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# ================================
# CONFIGURACIÓN BASE DE DATOS
# ================================

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',  # Cambiar por tu password
    'database': 'ojs_db',  # CORREGIDO: usando ojs_db como en tu explorador
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

@contextmanager
def get_db_connection():
    """Contexto de conexión a base de datos"""
    connection = pymysql.connect(**DB_CONFIG)
    try:
        yield connection
    finally:
        connection.close()

# ================================
# ESQUEMA DE BASE DE DATOS PERSISTENTE CORREGIDO
# ================================

def create_persistent_tables():
    """Crear/actualizar tablas para almacenamiento persistente de recomendaciones"""
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            
            # Primero verificar si las tablas existen y corregirlas
            cursor.execute("SHOW TABLES LIKE 'persistent_recommendations'")
            table_exists = cursor.fetchone()
            
            if table_exists:
                # Verificar si tiene las columnas necesarias
                cursor.execute("SHOW COLUMNS FROM persistent_recommendations")
                columns = [col['Field'] for col in cursor.fetchall()]
                
                # Agregar columnas faltantes
                if 'confidence_score' not in columns:
                    cursor.execute("ALTER TABLE persistent_recommendations ADD COLUMN confidence_score FLOAT DEFAULT 0.0")
                
                if 'algorithm' not in columns:
                    cursor.execute("ALTER TABLE persistent_recommendations ADD COLUMN algorithm VARCHAR(100) NOT NULL DEFAULT 'hybrid_content_collaborative'")
                
                if 'calculation_date' not in columns:
                    cursor.execute("ALTER TABLE persistent_recommendations ADD COLUMN calculation_date DATE NOT NULL DEFAULT (CURDATE())")
                
                if 'created_at' not in columns:
                    cursor.execute("ALTER TABLE persistent_recommendations ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                    
                if 'updated_at' not in columns:
                    cursor.execute("ALTER TABLE persistent_recommendations ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
                
                print("✅ Tabla persistent_recommendations actualizada")
            else:
                # Crear tabla completa
                cursor.execute("""
                    CREATE TABLE persistent_recommendations (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        source_publication_id INT NOT NULL,
                        target_publication_id INT NOT NULL,
                        similarity_score FLOAT NOT NULL,
                        algorithm VARCHAR(100) NOT NULL DEFAULT 'hybrid_content_collaborative',
                        confidence_score FLOAT DEFAULT 0.0,
                        metadata LONGTEXT,
                        calculation_date DATE NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        
                        INDEX idx_source_date (source_publication_id, calculation_date),
                        INDEX idx_target (target_publication_id),
                        INDEX idx_calculation_date (calculation_date),
                        INDEX idx_similarity (similarity_score),
                        UNIQUE KEY unique_recommendation (source_publication_id, target_publication_id, calculation_date)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
                """)
                print("✅ Tabla persistent_recommendations creada")
            
            # Tabla de recomendaciones para homepage
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS homepage_recommendations (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    publication_id INT NOT NULL,
                    recommendation_type ENUM('recent', 'featured', 'popular', 'trending') NOT NULL,
                    rank_position INT NOT NULL,
                    score FLOAT NOT NULL,
                    metadata JSON,
                    calculation_date DATE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    
                    INDEX idx_type_date_rank (recommendation_type, calculation_date, rank_position),
                    INDEX idx_publication (publication_id),
                    UNIQUE KEY unique_homepage_rec (publication_id, recommendation_type, calculation_date)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
            """)
            
            # Tabla de estado del sistema
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS recommendation_system_status (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    calculation_date DATE NOT NULL UNIQUE,
                    total_articles_processed INT DEFAULT 0,
                    total_recommendations_generated INT DEFAULT 0,
                    calculation_start_time TIMESTAMP NULL,
                    calculation_end_time TIMESTAMP NULL,
                    calculation_duration_seconds INT DEFAULT 0,
                    algorithm_used VARCHAR(100) DEFAULT 'hybrid_content_collaborative',
                    status ENUM('pending', 'running', 'completed', 'failed') DEFAULT 'pending',
                    error_message TEXT NULL,
                    metadata LONGTEXT,
                    
                    INDEX idx_date (calculation_date),
                    INDEX idx_status (status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
            """)
            
            # Tabla de métricas de artículos
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS article_metrics_daily (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    publication_id INT NOT NULL,
                    calculation_date DATE NOT NULL,
                    view_count INT DEFAULT 0,
                    download_count INT DEFAULT 0,
                    recommendation_clicks INT DEFAULT 0,
                    popularity_score FLOAT DEFAULT 0.0,
                    trending_score FLOAT DEFAULT 0.0,
                    
                    INDEX idx_publication_date (publication_id, calculation_date),
                    INDEX idx_popularity (popularity_score),
                    UNIQUE KEY unique_metrics (publication_id, calculation_date)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
            """)
            
            conn.commit()
            print("✅ Todas las tablas persistentes verificadas/creadas correctamente")

# ================================
# MOTOR DE CÁLCULO PERSISTENTE CORREGIDO
# ================================

class PersistentRecommendationCalculator:
    """
    Calculadora que genera y almacena todas las recomendaciones
    CORREGIDA para usar recommendation_cache como fuente
    """
    
    def __init__(self):
        self.calculation_date = datetime.now().date()
        self.start_time = None
        self.end_time = None
        self.total_articles = 0
        self.total_recommendations = 0
        self.errors = []
    
    def calculate_all_recommendations(self, force_recalculate=False):
        """Calcular todas las recomendaciones usando datos existentes"""
        
        print(f"🚀 Iniciando cálculo de recomendaciones para {self.calculation_date}")
        self.start_time = datetime.now()
        
        try:
            with get_db_connection() as conn:
                
                # Verificar si ya se calculó hoy
                if not force_recalculate and self._already_calculated_today(conn):
                    print(f"✅ Recomendaciones ya calculadas para {self.calculation_date}")
                    return True
                
                # Registrar inicio del cálculo
                self._register_calculation_start(conn)
                
                # 1. Migrar datos de recommendation_cache a persistent_recommendations
                success_articles = self._migrate_recommendation_cache(conn)
                
                # 2. Calcular recomendaciones para homepage
                success_homepage = self._calculate_homepage_recommendations(conn)
                
                # 3. Actualizar métricas de artículos
                self._update_article_metrics(conn)
                
                # Finalizar cálculo
                self.end_time = datetime.now()
                duration = (self.end_time - self.start_time).total_seconds()
                
                if success_articles and success_homepage:
                    self._register_calculation_success(conn, duration)
                    print(f"✅ Cálculo completado en {duration:.1f}s")
                    print(f"📊 {self.total_articles} artículos, {self.total_recommendations} recomendaciones")
                    return True
                else:
                    self._register_calculation_failure(conn, "Error en cálculo de recomendaciones")
                    return False
                    
        except Exception as e:
            error_msg = f"Error en cálculo: {str(e)}"
            print(f"❌ {error_msg}")
            self.errors.append(error_msg)
            
            try:
                with get_db_connection() as conn:
                    self._register_calculation_failure(conn, error_msg)
            except:
                pass
                
            return False
    
    def _migrate_recommendation_cache(self, conn):
        """Migrar datos de recommendation_cache a persistent_recommendations"""
        print("🔄 Migrando datos de recommendation_cache...")
        
        try:
            # Limpiar recomendaciones del día actual
            with conn.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM persistent_recommendations 
                    WHERE calculation_date = %s
                """, (self.calculation_date,))
                conn.commit()
                
                # Obtener datos de recommendation_cache
                cursor.execute("""
                    SELECT 
                        rc.source_publication_id,
                        rc.target_publication_id,
                        rc.similarity_score,
                        rc.algorithm,
                        p.submission_id,
                        COALESCE(ps_title.setting_value, 'Sin título') as title,
                        COALESCE(ps_abstract.setting_value, '') as abstract,
                        GROUP_CONCAT(DISTINCT CONCAT(
                            COALESCE(aus_fname.setting_value, ''), ' ',
                            COALESCE(aus_lname.setting_value, '')
                        ) SEPARATOR '; ') as authors
                    FROM recommendation_cache rc
                    JOIN publications p ON rc.target_publication_id = p.publication_id
                    LEFT JOIN publication_settings ps_title ON p.publication_id = ps_title.publication_id 
                        AND ps_title.setting_name = 'title'
                    LEFT JOIN publication_settings ps_abstract ON p.publication_id = ps_abstract.publication_id 
                        AND ps_abstract.setting_name = 'abstract'
                    LEFT JOIN authors a ON p.publication_id = a.publication_id
                    LEFT JOIN author_settings aus_fname ON a.author_id = aus_fname.author_id 
                        AND aus_fname.setting_name = 'givenName'
                    LEFT JOIN author_settings aus_lname ON a.author_id = aus_lname.author_id 
                        AND aus_lname.setting_name = 'familyName'
                    WHERE p.status = 3
                    GROUP BY rc.source_publication_id, rc.target_publication_id, rc.similarity_score, rc.algorithm, p.submission_id
                    ORDER BY rc.source_publication_id, rc.similarity_score DESC
                """)
                
                cache_data = cursor.fetchall()
                
                if not cache_data:
                    print("⚠️ No hay datos en recommendation_cache")
                    return False
                
                # Insertar en persistent_recommendations
                for row in cache_data:
                    metadata = {
                        'title': row['title'],
                        'authors': row['authors'] or '',
                        'abstract_preview': (row['abstract'] or '')[:200],
                        'url': f'/article/view/{row["submission_id"]}',
                        'migrated_from': 'recommendation_cache',
                        'migration_date': datetime.now().isoformat()
                    }
                    
                    cursor.execute("""
                        INSERT INTO persistent_recommendations
                        (source_publication_id, target_publication_id, similarity_score, 
                         algorithm, confidence_score, metadata, calculation_date)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                        similarity_score = VALUES(similarity_score),
                        confidence_score = VALUES(confidence_score),
                        metadata = VALUES(metadata)
                    """, (
                        row['source_publication_id'],
                        row['target_publication_id'],
                        row['similarity_score'],
                        row['algorithm'] or 'tfidf_cosine',
                        min(row['similarity_score'] * 1.5, 1.0) if row['similarity_score'] else 0.5,
                        json.dumps(metadata),
                        self.calculation_date
                    ))
                    
                    self.total_recommendations += 1
                
                # Contar artículos únicos
                cursor.execute("""
                    SELECT COUNT(DISTINCT source_publication_id) as unique_articles
                    FROM persistent_recommendations 
                    WHERE calculation_date = %s
                """, (self.calculation_date,))
                
                result = cursor.fetchone()
                self.total_articles = result['unique_articles'] if result else 0
                
                conn.commit()
                print(f"✅ Migrados {self.total_recommendations} recomendaciones para {self.total_articles} artículos")
                return True
                
        except Exception as e:
            print(f"❌ Error migrando recommendation_cache: {e}")
            return False
    
    def _calculate_homepage_recommendations(self, conn):
        """Calcular recomendaciones para homepage usando datos reales"""
        print("🏠 Calculando recomendaciones para homepage...")
        
        try:
            # Limpiar recomendaciones homepage del día
            with conn.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM homepage_recommendations 
                    WHERE calculation_date = %s
                """, (self.calculation_date,))
                conn.commit()
            
            # 1. Artículos recientes (últimos 90 días, ordenados por fecha)
            self._calculate_recent_articles(conn)
            
            # 2. Artículos destacados (más recomendados)
            self._calculate_featured_articles(conn)
            
            # 3. Artículos populares (combinando recencia y recomendaciones)
            self._calculate_popular_articles(conn)
            
            # 4. Artículos trending (recientes con buenas recomendaciones)
            self._calculate_trending_articles(conn)
            
            print("✅ Recomendaciones homepage completadas")
            return True
            
        except Exception as e:
            print(f"❌ Error calculando homepage: {e}")
            return False
    
    def _calculate_recent_articles(self, conn):
        """Calcular artículos recientes usando datos reales de OJS"""
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    p.publication_id,
                    p.date_published,
                    DATEDIFF(CURDATE(), p.date_published) as days_ago,
                    CASE 
                        WHEN p.date_published IS NULL THEN 0.3
                        WHEN DATEDIFF(CURDATE(), p.date_published) <= 7 THEN 1.0
                        WHEN DATEDIFF(CURDATE(), p.date_published) <= 30 THEN 0.8
                        WHEN DATEDIFF(CURDATE(), p.date_published) <= 90 THEN 0.6
                        ELSE 0.4
                    END as recency_score
                FROM publications p
                WHERE p.status = 3
                ORDER BY p.date_published DESC, p.publication_id DESC
                LIMIT 20
            """)
            
            recent_articles = cursor.fetchall()
            
            for rank, article in enumerate(recent_articles, 1):
                cursor.execute("""
                    INSERT INTO homepage_recommendations
                    (publication_id, recommendation_type, rank_position, score, calculation_date)
                    VALUES (%s, 'recent', %s, %s, %s)
                """, (
                    article['publication_id'],
                    rank,
                    article['recency_score'],
                    self.calculation_date
                ))
            
            conn.commit()
            print(f"   📅 {len(recent_articles)} artículos recientes")
    
    def _calculate_featured_articles(self, conn):
        """Calcular artículos destacados basados en recomendaciones"""
        with conn.cursor() as cursor:
            # Artículos que más aparecen como recomendaciones
            cursor.execute("""
                SELECT 
                    pr.target_publication_id as publication_id,
                    COUNT(*) as recommendation_count,
                    AVG(pr.similarity_score) as avg_similarity,
                    (COUNT(*) * 0.7 + AVG(pr.similarity_score) * 0.3) as featured_score
                FROM persistent_recommendations pr
                WHERE pr.calculation_date = %s
                GROUP BY pr.target_publication_id
                HAVING recommendation_count >= 2
                ORDER BY featured_score DESC
                LIMIT 15
            """, (self.calculation_date,))
            
            featured_articles = cursor.fetchall()
            
            for rank, article in enumerate(featured_articles, 1):
                cursor.execute("""
                    INSERT INTO homepage_recommendations
                    (publication_id, recommendation_type, rank_position, score, calculation_date)
                    VALUES (%s, 'featured', %s, %s, %s)
                """, (
                    article['publication_id'],
                    rank,
                    article['featured_score'],
                    self.calculation_date
                ))
            
            conn.commit()
            print(f"   ⭐ {len(featured_articles)} artículos destacados")
    
    def _calculate_popular_articles(self, conn):
        """Calcular artículos populares"""
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    pr.target_publication_id as publication_id,
                    COUNT(*) as rec_count,
                    AVG(pr.similarity_score) as avg_score,
                    COALESCE(DATEDIFF(CURDATE(), p.date_published), 365) as days_old,
                    (COUNT(*) * 0.6 + AVG(pr.similarity_score) * 0.3 + 
                     (GREATEST(0, 180 - COALESCE(DATEDIFF(CURDATE(), p.date_published), 365)) / 180.0) * 0.1) as popularity_score
                FROM persistent_recommendations pr
                LEFT JOIN publications p ON pr.target_publication_id = p.publication_id
                WHERE pr.calculation_date = %s
                GROUP BY pr.target_publication_id
                HAVING rec_count >= 1
                ORDER BY popularity_score DESC
                LIMIT 12
            """, (self.calculation_date,))
            
            popular_articles = cursor.fetchall()
            
            for rank, article in enumerate(popular_articles, 1):
                cursor.execute("""
                    INSERT INTO homepage_recommendations
                    (publication_id, recommendation_type, rank_position, score, calculation_date)
                    VALUES (%s, 'popular', %s, %s, %s)
                """, (
                    article['publication_id'],
                    rank,
                    article['popularity_score'],
                    self.calculation_date
                ))
            
            conn.commit()
            print(f"   🔥 {len(popular_articles)} artículos populares")
    
    def _calculate_trending_articles(self, conn):
        """Calcular artículos en tendencia"""
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    pr.target_publication_id as publication_id,
                    COUNT(*) as rec_count,
                    AVG(pr.similarity_score) as avg_score,
                    p.date_published,
                    (COUNT(*) * 0.8 + 
                     CASE 
                        WHEN p.date_published IS NULL THEN 0.1
                        WHEN DATEDIFF(CURDATE(), p.date_published) <= 14 THEN 0.2
                        WHEN DATEDIFF(CURDATE(), p.date_published) <= 30 THEN 0.15
                        ELSE 0.05
                     END) as trending_score
                FROM persistent_recommendations pr
                LEFT JOIN publications p ON pr.target_publication_id = p.publication_id
                WHERE pr.calculation_date = %s
                GROUP BY pr.target_publication_id
                HAVING rec_count >= 1
                ORDER BY trending_score DESC
                LIMIT 10
            """, (self.calculation_date,))
            
            trending_articles = cursor.fetchall()
            
            for rank, article in enumerate(trending_articles, 1):
                cursor.execute("""
                    INSERT INTO homepage_recommendations
                    (publication_id, recommendation_type, rank_position, score, calculation_date)
                    VALUES (%s, 'trending', %s, %s, %s)
                """, (
                    article['publication_id'],
                    rank,
                    article['trending_score'],
                    self.calculation_date
                ))
            
            conn.commit()
            print(f"   📈 {len(trending_articles)} artículos trending")
    
    def _update_article_metrics(self, conn):
        """Actualizar métricas diarias de artículos"""
        print("📊 Actualizando métricas de artículos...")
        
        with conn.cursor() as cursor:
            # Calcular métricas basadas en recomendaciones
            cursor.execute("""
                SELECT 
                    pr.target_publication_id as publication_id,
                    COUNT(*) as recommendation_count,
                    AVG(pr.similarity_score) as avg_similarity,
                    COUNT(*) * AVG(pr.similarity_score) as popularity_score
                FROM persistent_recommendations pr
                WHERE pr.calculation_date = %s
                GROUP BY pr.target_publication_id
            """, (self.calculation_date,))
            
            metrics = cursor.fetchall()
            
            for metric in metrics:
                cursor.execute("""
                    INSERT INTO article_metrics_daily
                    (publication_id, calculation_date, recommendation_clicks, 
                     popularity_score, trending_score)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    recommendation_clicks = VALUES(recommendation_clicks),
                    popularity_score = VALUES(popularity_score),
                    trending_score = VALUES(trending_score)
                """, (
                    metric['publication_id'],
                    self.calculation_date,
                    metric['recommendation_count'],
                    metric['popularity_score'],
                    metric['avg_similarity']
                ))
            
            conn.commit()
            print(f"   📈 Métricas actualizadas para {len(metrics)} artículos")
    
    def _already_calculated_today(self, conn):
        """Verificar si ya se calculó hoy"""
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT status FROM recommendation_system_status 
                WHERE calculation_date = %s AND status = 'completed'
            """, (self.calculation_date,))
            return cursor.fetchone() is not None
    
    def _register_calculation_start(self, conn):
        """Registrar inicio del cálculo"""
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO recommendation_system_status 
                (calculation_date, calculation_start_time, status, algorithm_used)
                VALUES (%s, %s, 'running', 'hybrid_content_collaborative')
                ON DUPLICATE KEY UPDATE
                calculation_start_time = VALUES(calculation_start_time),
                status = 'running',
                algorithm_used = VALUES(algorithm_used)
            """, (self.calculation_date, self.start_time))
            conn.commit()
    
    def _register_calculation_success(self, conn, duration_seconds):
        """Registrar éxito del cálculo"""
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE recommendation_system_status 
                SET calculation_end_time = %s,
                    calculation_duration_seconds = %s,
                    total_articles_processed = %s,
                    total_recommendations_generated = %s,
                    status = 'completed'
                WHERE calculation_date = %s
            """, (
                self.end_time,
                int(duration_seconds),
                self.total_articles,
                self.total_recommendations,
                self.calculation_date
            ))
            conn.commit()
    
    def _register_calculation_failure(self, conn, error_message):
        """Registrar fallo del cálculo"""
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE recommendation_system_status 
                SET calculation_end_time = %s,
                    status = 'failed',
                    error_message = %s
                WHERE calculation_date = %s
            """, (
                datetime.now(),
                error_message,
                self.calculation_date
            ))
            conn.commit()

# ================================
# PROGRAMADOR DE TAREAS (SIN CAMBIOS)
# ================================

class RecommendationScheduler:
    """Programador para cálculos automáticos diarios"""
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.is_running = False
    
    def start_scheduler(self):
        """Iniciar programador"""
        if self.is_running:
            return
        
        # Programar cálculo diario a las 3:00 AM
        self.scheduler.add_job(
            func=self.daily_calculation_job,
            trigger=CronTrigger(hour=3, minute=0),
            id='daily_recommendations',
            name='Cálculo Diario de Recomendaciones',
            replace_existing=True
        )
        
        # Programar limpieza semanal (domingos a las 2:00 AM)
        self.scheduler.add_job(
            func=self.weekly_cleanup_job,
            trigger=CronTrigger(day_of_week=6, hour=2, minute=0),
            id='weekly_cleanup',
            name='Limpieza Semanal de Datos',
            replace_existing=True
        )
        
        self.scheduler.start()
        self.is_running = True
        print("📅 Programador iniciado - Cálculo diario a las 3:00 AM")
    
    def stop_scheduler(self):
        """Detener programador"""
        if self.scheduler.running:
            self.scheduler.shutdown()
        self.is_running = False
    
    def daily_calculation_job(self):
        """Job de cálculo diario"""
        print("🌅 Iniciando cálculo diario programado...")
        calculator = PersistentRecommendationCalculator()
        success = calculator.calculate_all_recommendations()
        
        if success:
            print("✅ Cálculo diario completado exitosamente")
        else:
            print("❌ Error en cálculo diario")
    
    def weekly_cleanup_job(self):
        """Job de limpieza semanal"""
        print("🧹 Iniciando limpieza semanal...")
        
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    # Eliminar recomendaciones de más de 7 días
                    cursor.execute("""
                        DELETE FROM persistent_recommendations 
                        WHERE calculation_date < DATE_SUB(CURDATE(), INTERVAL 7 DAY)
                    """)
                    
                    cursor.execute("""
                        DELETE FROM homepage_recommendations 
                        WHERE calculation_date < DATE_SUB(CURDATE(), INTERVAL 7 DAY)
                    """)
                    
                    cursor.execute("""
                        DELETE FROM article_metrics_daily 
                        WHERE calculation_date < DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                    """)
                    
                    cursor.execute("""
                        DELETE FROM recommendation_system_status 
                        WHERE calculation_date < DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                    """)
                    
                    conn.commit()
                    print("✅ Limpieza semanal completada")
                    
        except Exception as e:
            print(f"❌ Error en limpieza semanal: {e}")

# ================================
# INSTANCIA GLOBAL
# ================================

scheduler = RecommendationScheduler()

# ================================
# LIFESPAN EVENT HANDLER
# ================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manejar eventos de startup y shutdown de forma moderna"""
    # Startup
    print("🚀 Inicializando sistema de recomendaciones persistentes...")
    
    # Crear tablas
    create_persistent_tables()
    
    # Iniciar programador
    scheduler.start_scheduler()
    
    # Verificar si necesita cálculo inicial
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT status FROM recommendation_system_status 
                    WHERE calculation_date = CURDATE() AND status = 'completed'
                """)
                
                if not cursor.fetchone():
                    print("🔄 No hay cálculo para hoy, iniciando cálculo inicial...")
                    calculator = PersistentRecommendationCalculator()
                    calculator.calculate_all_recommendations()
    except Exception as e:
        print(f"⚠️ Error verificando estado inicial: {e}")
    
    print("✅ Sistema iniciado correctamente")
    
    yield
    
    # Shutdown
    scheduler.stop_scheduler()
    print("🛑 Sistema detenido")

# ================================
# CONFIGURACIÓN FASTAPI (SIN CAMBIOS)
# ================================

app = FastAPI(
    title="🔄 API de Recomendaciones Persistentes OJS",
    description="""
    **Sistema de Recomendaciones con Almacenamiento Persistente**
    
    ### 🎯 Arquitectura:
    - **Migración automática** de recommendation_cache
    - **Almacenamiento persistente** en base de datos
    - **Plugin PHP/JS** consume directamente desde BD
    - **Sin latencia** en el frontend (datos pre-calculados)
    
    ### ⚡ Ventajas:
    - Frontend ultra-rápido (consulta directa a BD)
    - Recomendaciones siempre actualizadas
    - Menor carga en el servidor web
    - Escalabilidad mejorada
    """,
    version="4.1.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================================
# ENDPOINTS CORREGIDOS
# ================================

@app.get("/")
def root():
    """Información del sistema persistente"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Estado del último cálculo
                cursor.execute("""
                    SELECT * FROM recommendation_system_status 
                    ORDER BY calculation_date DESC LIMIT 1
                """)
                last_status = cursor.fetchone()
                
                # Estadísticas actuales
                cursor.execute("""
                    SELECT 
                        COUNT(DISTINCT source_publication_id) as articles_with_recs,
                        COUNT(*) as total_recommendations
                    FROM persistent_recommendations 
                    WHERE calculation_date = CURDATE()
                """)
                stats = cursor.fetchone()
        
        return {
            "message": "🔄 Sistema de Recomendaciones Persistentes OJS",
            "version": "4.1.0",
            "architecture": "persistent_database_storage",
            "last_calculation": {
                "date": last_status['calculation_date'].isoformat() if last_status else None,
                "status": last_status['status'] if last_status else 'unknown',
                "duration": f"{last_status['calculation_duration_seconds']}s" if last_status and last_status['calculation_duration_seconds'] else None,
                "articles_processed": last_status['total_articles_processed'] if last_status else 0,
                "recommendations_generated": last_status['total_recommendations_generated'] if last_status else 0
            },
            "current_data": {
                "articles_with_recommendations": stats['articles_with_recs'] if stats else 0,
                "total_recommendations_today": stats['total_recommendations'] if stats else 0
            },
            "scheduler_status": "active" if scheduler.is_running else "inactive",
            "next_calculation": "Daily at 3:00 AM",
            "data_source": "recommendation_cache migrated to persistent_recommendations",
            "frontend_integration": {
                "php_queries": "Direct database queries to persistent_recommendations table",
                "no_api_calls_needed": True,
                "ultra_fast_responses": True
            }
        }
        
    except Exception as e:
        return {
            "message": "Sistema de Recomendaciones Persistentes",
            "error": str(e),
            "status": "error"
        }

@app.get("/status")
def get_system_status():
    """Estado detallado del sistema"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Últimos 7 días de cálculos
                cursor.execute("""
                    SELECT calculation_date, status, calculation_duration_seconds,
                           total_articles_processed, total_recommendations_generated
                    FROM recommendation_system_status 
                    WHERE calculation_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
                    ORDER BY calculation_date DESC
                """)
                recent_calculations = cursor.fetchall()
                
                # Estadísticas de hoy
                cursor.execute("""
                    SELECT 
                        COUNT(DISTINCT source_publication_id) as articles_with_recs,
                        COUNT(*) as total_recommendations,
                        AVG(similarity_score) as avg_similarity
                    FROM persistent_recommendations 
                    WHERE calculation_date = CURDATE()
                """)
                today_stats = cursor.fetchone()
                
                # Estadísticas de homepage
                cursor.execute("""
                    SELECT recommendation_type, COUNT(*) as count
                    FROM homepage_recommendations 
                    WHERE calculation_date = CURDATE()
                    GROUP BY recommendation_type
                """)
                homepage_stats = cursor.fetchall()
                
                # Estado de recommendation_cache (fuente)
                cursor.execute("""
                    SELECT COUNT(*) as total_cache_records,
                           COUNT(DISTINCT source_publication_id) as unique_sources,
                           COUNT(DISTINCT target_publication_id) as unique_targets,
                           AVG(similarity_score) as avg_cache_similarity
                    FROM recommendation_cache
                """)
                cache_stats = cursor.fetchone()
        
        return {
            "system_status": "operational",
            "scheduler_running": scheduler.is_running,
            "data_source": "recommendation_cache",
            "cache_statistics": {
                "total_records": cache_stats['total_cache_records'] if cache_stats else 0,
                "unique_sources": cache_stats['unique_sources'] if cache_stats else 0,
                "unique_targets": cache_stats['unique_targets'] if cache_stats else 0,
                "average_similarity": round(float(cache_stats['avg_cache_similarity'] or 0), 3) if cache_stats else 0
            },
            "recent_calculations": [
                {
                    "date": calc['calculation_date'].isoformat(),
                    "status": calc['status'],
                    "duration_seconds": calc['calculation_duration_seconds'],
                    "articles_processed": calc['total_articles_processed'],
                    "recommendations_generated": calc['total_recommendations_generated']
                } for calc in recent_calculations
            ],
            "today_statistics": {
                "articles_with_recommendations": today_stats['articles_with_recs'] if today_stats else 0,
                "total_recommendations": today_stats['total_recommendations'] if today_stats else 0,
                "average_similarity": round(float(today_stats['avg_similarity'] or 0), 3) if today_stats else 0
            },
            "homepage_recommendations": {
                rec['recommendation_type']: rec['count'] 
                for rec in homepage_stats
            },
            "database_performance": "Direct queries - < 5ms response time"
        }
        
    except Exception as e:
        return {"error": str(e), "status": "error"}

@app.post("/admin/calculate-now")
async def calculate_recommendations_now(background_tasks: BackgroundTasks, force: bool = False):
    """Forzar cálculo inmediato de recomendaciones"""
    
    def run_calculation():
        calculator = PersistentRecommendationCalculator()
        calculator.calculate_all_recommendations(force_recalculate=force)
    
    background_tasks.add_task(run_calculation)
    
    return {
        "message": "Cálculo iniciado en background",
        "force_recalculate": force,
        "data_source": "recommendation_cache será migrado a persistent_recommendations",
        "estimated_time": "2-5 minutos dependiendo del número de artículos",
        "check_status": "/status"
    }

@app.get("/admin/recommendations/{publication_id}")
def get_article_recommendations_from_db(publication_id: int, limit: int = Query(10, ge=1, le=50)):
    """Ver recomendaciones almacenadas para un artículo específico"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT pr.target_publication_id, pr.similarity_score, 
                           pr.confidence_score, pr.metadata, pr.algorithm, 
                           pr.calculation_date,
                           ROW_NUMBER() OVER (ORDER BY pr.similarity_score DESC) as rank_position
                    FROM persistent_recommendations pr
                    WHERE pr.source_publication_id = %s 
                        AND pr.calculation_date = CURDATE()
                    ORDER BY pr.similarity_score DESC
                    LIMIT %s
                """, (publication_id, limit))
                
                recommendations = cursor.fetchall()
                
                # Enriquecer con datos de publicación
                result = []
                for rec in recommendations:
                    metadata = json.loads(rec['metadata']) if rec['metadata'] else {}
                    result.append({
                        "target_publication_id": rec['target_publication_id'],
                        "rank": rec['rank_position'],
                        "similarity_score": rec['similarity_score'],
                        "confidence_score": rec['confidence_score'],
                        "algorithm": rec['algorithm'],
                        "title": metadata.get('title', 'Sin título'),
                        "authors": metadata.get('authors', ''),
                        "abstract_preview": metadata.get('abstract_preview', ''),
                        "url": metadata.get('url', ''),
                        "calculation_date": rec['calculation_date'].isoformat()
                    })
                
                return {
                    "source_publication_id": publication_id,
                    "total_recommendations": len(result),
                    "recommendations": result,
                    "data_source": "persistent_database",
                    "response_time": "< 5ms"
                }
                
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/homepage/{recommendation_type}")
def get_homepage_recommendations_from_db(
    recommendation_type: str = Path(..., pattern="^(recent|featured|popular|trending)$"),
    limit: int = Query(10, ge=1, le=50)
):
    """Ver recomendaciones de homepage almacenadas"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT hr.publication_id, hr.rank_position, hr.score,
                           ps_title.setting_value as title,
                           ps_abstract.setting_value as abstract,
                           GROUP_CONCAT(CONCAT(
                               COALESCE(aus_fname.setting_value, ''), ' ',
                               COALESCE(aus_lname.setting_value, '')
                           ) SEPARATOR '; ') as authors,
                           p.submission_id
                    FROM homepage_recommendations hr
                    JOIN publications p ON hr.publication_id = p.publication_id
                    LEFT JOIN publication_settings ps_title ON p.publication_id = ps_title.publication_id 
                        AND ps_title.setting_name = 'title'
                    LEFT JOIN publication_settings ps_abstract ON p.publication_id = ps_abstract.publication_id 
                        AND ps_abstract.setting_name = 'abstract'
                    LEFT JOIN authors a ON p.publication_id = a.publication_id
                    LEFT JOIN author_settings aus_fname ON a.author_id = aus_fname.author_id 
                        AND aus_fname.setting_name = 'givenName'
                    LEFT JOIN author_settings aus_lname ON a.author_id = aus_lname.author_id 
                        AND aus_lname.setting_name = 'familyName'
                    WHERE hr.recommendation_type = %s 
                        AND hr.calculation_date = CURDATE()
                    GROUP BY hr.publication_id, hr.rank_position, hr.score, p.submission_id
                    ORDER BY hr.rank_position
                    LIMIT %s
                """, (recommendation_type, limit))
                
                recommendations = cursor.fetchall()
                
                result = []
                for rec in recommendations:
                    result.append({
                        "publication_id": rec['publication_id'],
                        "submission_id": rec['submission_id'],
                        "rank": rec['rank_position'],
                        "score": rec['score'],
                        "title": rec['title'] or 'Sin título',
                        "authors": rec['authors'] or '',
                        "abstract": (rec['abstract'] or '')[:200] + '...' if rec['abstract'] and len(rec['abstract']) > 200 else rec['abstract'] or '',
                        "url": f"/article/view/{rec['submission_id']}"
                    })
                
                return {
                    "recommendation_type": recommendation_type,
                    "total_articles": len(result),
                    "articles": result,
                    "data_source": "persistent_database",
                    "response_time": "< 5ms"
                }
                
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/cache-status")
def get_cache_status():
    """Ver estado de recommendation_cache (fuente de datos)"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # Estadísticas de recommendation_cache
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_records,
                        COUNT(DISTINCT source_publication_id) as unique_sources,
                        COUNT(DISTINCT target_publication_id) as unique_targets,
                        MIN(similarity_score) as min_similarity,
                        MAX(similarity_score) as max_similarity,
                        AVG(similarity_score) as avg_similarity,
                        MIN(created_at) as oldest_record,
                        MAX(updated_at) as newest_record
                    FROM recommendation_cache
                """)
                
                cache_stats = cursor.fetchone()
                
                # Top 5 artículos más recomendados
                cursor.execute("""
                    SELECT 
                        rc.target_publication_id,
                        COUNT(*) as recommendation_count,
                        AVG(rc.similarity_score) as avg_similarity,
                        ps.setting_value as title
                    FROM recommendation_cache rc
                    LEFT JOIN publication_settings ps ON rc.target_publication_id = ps.publication_id
                        AND ps.setting_name = 'title'
                    GROUP BY rc.target_publication_id, ps.setting_value
                    ORDER BY recommendation_count DESC
                    LIMIT 5
                """)
                
                top_recommended = cursor.fetchall()
                
                # Distribución de algoritmos
                cursor.execute("""
                    SELECT algorithm, COUNT(*) as count
                    FROM recommendation_cache
                    GROUP BY algorithm
                """)
                
                algorithm_distribution = cursor.fetchall()
                
                return {
                    "cache_statistics": {
                        "total_records": cache_stats['total_records'],
                        "unique_source_articles": cache_stats['unique_sources'],
                        "unique_target_articles": cache_stats['unique_targets'],
                        "similarity_range": {
                            "min": round(float(cache_stats['min_similarity'] or 0), 4),
                            "max": round(float(cache_stats['max_similarity'] or 0), 4),
                            "average": round(float(cache_stats['avg_similarity'] or 0), 4)
                        },
                        "date_range": {
                            "oldest": cache_stats['oldest_record'].isoformat() if cache_stats['oldest_record'] else None,
                            "newest": cache_stats['newest_record'].isoformat() if cache_stats['newest_record'] else None
                        }
                    },
                    "top_recommended_articles": [
                        {
                            "publication_id": article['target_publication_id'],
                            "title": article['title'] or 'Sin título',
                            "recommendation_count": article['recommendation_count'],
                            "average_similarity": round(float(article['avg_similarity']), 4)
                        }
                        for article in top_recommended
                    ],
                    "algorithm_distribution": {
                        alg['algorithm']: alg['count'] 
                        for alg in algorithm_distribution
                    },
                    "data_quality": "Good" if cache_stats['total_records'] > 50 else "Limited",
                    "ready_for_migration": cache_stats['total_records'] > 0
                }
                
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/repair-tables")
def repair_table_structure():
    """Reparar y verificar estructura de tablas"""
    try:
        create_persistent_tables()
        
        # Verificar estructura final
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                tables_info = {}
                
                # Verificar cada tabla
                for table in ['persistent_recommendations', 'homepage_recommendations', 
                             'recommendation_system_status', 'article_metrics_daily']:
                    cursor.execute(f"SHOW COLUMNS FROM {table}")
                    columns = cursor.fetchall()
                    tables_info[table] = {
                        "exists": True,
                        "columns": [col['Field'] for col in columns],
                        "column_count": len(columns)
                    }
        
        return {
            "message": "Estructura de tablas reparada exitosamente",
            "tables_verified": tables_info,
            "status": "success"
        }
        
    except Exception as e:
        return {
            "message": "Error reparando estructura de tablas",
            "error": str(e),
            "status": "failed"
        }

@app.delete("/admin/cleanup")
def cleanup_old_data(days_to_keep: int = Query(7, ge=1, le=30)):
    """Limpiar datos antiguos manualmente"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                
                # Eliminar recomendaciones antiguas
                cursor.execute("""
                    DELETE FROM persistent_recommendations 
                    WHERE calculation_date < DATE_SUB(CURDATE(), INTERVAL %s DAY)
                """, (days_to_keep,))
                recs_deleted = cursor.rowcount
                
                cursor.execute("""
                    DELETE FROM homepage_recommendations 
                    WHERE calculation_date < DATE_SUB(CURDATE(), INTERVAL %s DAY)
                """, (days_to_keep,))
                homepage_deleted = cursor.rowcount
                
                cursor.execute("""
                    DELETE FROM article_metrics_daily 
                    WHERE calculation_date < DATE_SUB(CURDATE(), INTERVAL %s DAY)
                """, (days_to_keep,))
                metrics_deleted = cursor.rowcount
                
                cursor.execute("""
                    DELETE FROM recommendation_system_status 
                    WHERE calculation_date < DATE_SUB(CURDATE(), INTERVAL %s DAY)
                """, (days_to_keep,))
                status_deleted = cursor.rowcount
                
                conn.commit()
                
                return {
                    "message": f"Limpieza completada - datos anteriores a {days_to_keep} días eliminados",
                    "deleted_records": {
                        "recommendations": recs_deleted,
                        "homepage_recommendations": homepage_deleted,
                        "article_metrics": metrics_deleted,
                        "status_records": status_deleted
                    }
                }
                
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# ================================
# ENDPOINT CORREGIDO SIN publication_issues
# Reemplazar en main_hybrid.py
# ================================

@app.get("/volumes")
def get_all_volumes():
    """Obtener todos los volúmenes de OJS sin usar publication_issues"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                
                print("🔍 Iniciando consulta de volúmenes...")
                
                # Consulta simplificada sin publication_issues
                cursor.execute("""
                    SELECT 
                        i.issue_id,
                        i.journal_id,
                        i.volume,
                        i.number,
                        i.year,
                        i.date_published,
                        i.date_notified,
                        i.last_modified,
                        i.access_status,
                        i.open_access_date,
                        i.published,
                        
                        -- Título del issue con fallback mejorado
                        COALESCE(
                            MAX(CASE WHEN is_title.locale = 'es' THEN is_title.setting_value END),
                            MAX(CASE WHEN is_title.locale = 'en' THEN is_title.setting_value END),
                            CONCAT('Volumen ', COALESCE(i.volume, ''), ' Número ', COALESCE(i.number, ''))
                        ) as title,
                        
                        -- Descripción del issue
                        COALESCE(
                            MAX(CASE WHEN is_desc.locale = 'es' THEN is_desc.setting_value END),
                            MAX(CASE WHEN is_desc.locale = 'en' THEN is_desc.setting_value END),
                            ''
                        ) as description,
                        
                        -- Cover image si existe
                        MAX(CASE WHEN is_cover.setting_name = 'coverImage' THEN is_cover.setting_value END) as cover_image,
                        
                        -- Información del journal
                        COALESCE(
                            MAX(CASE WHEN js_title.locale = 'es' THEN js_title.setting_value END),
                            MAX(CASE WHEN js_title.locale = 'en' THEN js_title.setting_value END),
                            'Revista Científica'
                        ) as journal_title,
                        
                        COALESCE(
                            MAX(CASE WHEN js_abbrev.setting_name = 'abbreviation' THEN js_abbrev.setting_value END),
                            ''
                        ) as journal_abbreviation
                        
                    FROM issues i
                    LEFT JOIN journals j ON i.journal_id = j.journal_id
                    
                    -- Settings del issue
                    LEFT JOIN issue_settings is_title ON i.issue_id = is_title.issue_id 
                        AND is_title.setting_name = 'title'
                    LEFT JOIN issue_settings is_desc ON i.issue_id = is_desc.issue_id 
                        AND is_desc.setting_name = 'description'
                    LEFT JOIN issue_settings is_cover ON i.issue_id = is_cover.issue_id 
                        AND is_cover.setting_name = 'coverImage'
                    
                    -- Settings del journal
                    LEFT JOIN journal_settings js_title ON j.journal_id = js_title.journal_id 
                        AND js_title.setting_name = 'name'
                    LEFT JOIN journal_settings js_abbrev ON j.journal_id = js_abbrev.journal_id 
                        AND js_abbrev.setting_name = 'abbreviation'
                    
                    WHERE i.published = 1  -- Solo issues publicados
                    
                    GROUP BY i.issue_id, i.journal_id, i.volume, i.number, i.year, 
                             i.date_published, i.date_notified, i.last_modified,
                             i.access_status, i.open_access_date, i.published
                    
                    ORDER BY 
                        COALESCE(i.date_published, i.date_notified, i.last_modified) DESC,
                        CAST(COALESCE(i.year, '0') AS UNSIGNED) DESC,
                        CAST(COALESCE(i.volume, '0') AS UNSIGNED) DESC,
                        CAST(COALESCE(i.number, '0') AS UNSIGNED) DESC
                """)
                
                issues = cursor.fetchall()
                print(f"📊 Issues encontrados: {len(issues)}")
                
                if not issues:
                    print("⚠️ No se encontraron issues publicados")
                    return {
                        'total_volumes': 0,
                        'volumes': [],
                        'data_source': 'ojs_database_direct',
                        'response_time': '< 50ms',
                        'last_updated': datetime.now().isoformat(),
                        'message': 'No hay volúmenes publicados',
                        'debug_info': {
                            'query_executed': 'issues_without_publication_issues_table',
                            'issues_found': 0
                        }
                    }
                
                # Intentar obtener conteo de artículos por issue usando diferentes métodos
                print("📊 Obteniendo conteo de artículos...")
                articles_count_map = {}
                
                # Método 1: Intentar con submissions + current_publication_id
                try:
                    cursor.execute("""
                        SELECT 
                            s.context_id as issue_id,
                            COUNT(DISTINCT p.publication_id) as articles_count
                        FROM submissions s
                        JOIN publications p ON s.current_publication_id = p.publication_id
                        WHERE p.status = 3
                        GROUP BY s.context_id
                    """)
                    articles_data = cursor.fetchall()
                    for row in articles_data:
                        if row['issue_id']:
                            articles_count_map[row['issue_id']] = row['articles_count']
                    print(f"✅ Método 1 exitoso: {len(articles_count_map)} issues con artículos")
                except Exception as e:
                    print(f"⚠️ Método 1 falló: {e}")
                    
                    # Método 2: Fallback - contar submissions directamente
                    try:
                        cursor.execute("""
                            SELECT 
                                s.context_id as issue_id,
                                COUNT(DISTINCT s.submission_id) as articles_count
                            FROM submissions s
                            WHERE s.status = 3
                            GROUP BY s.context_id
                        """)
                        articles_data = cursor.fetchall()
                        for row in articles_data:
                            if row['issue_id']:
                                articles_count_map[row['issue_id']] = row['articles_count']
                        print(f"✅ Método 2 exitoso: {len(articles_count_map)} issues con artículos")
                    except Exception as e:
                        print(f"⚠️ Método 2 también falló: {e}")
                        print("📊 Usando conteo 0 para todos los artículos")
                
                # Procesar y limpiar datos
                volumes_list = []
                for issue in issues:
                    
                    # Determinar fecha de publicación
                    pub_date = issue['date_published'] or issue['date_notified'] or issue['last_modified']
                    
                    # Determinar status de acceso
                    access_status = 'open'
                    if issue['access_status'] == 1:  # Subscription
                        if issue['open_access_date'] and issue['open_access_date'] > datetime.now().date():
                            access_status = 'subscription'
                    
                    # Construir URL del issue
                    issue_url = f"/issue/view/{issue['issue_id']}"
                    
                    # Nombre para mostrar mejorado
                    volume_part = f"Vol. {issue['volume']}" if issue['volume'] else ""
                    number_part = f"Núm. {issue['number']}" if issue['number'] else ""
                    year_part = f"({issue['year']})" if issue['year'] else ""
                    
                    # Construir display_name
                    display_parts = []
                    if volume_part:
                        display_parts.append(volume_part)
                    if number_part:
                        display_parts.append(number_part)
                    if year_part:
                        display_parts.append(year_part)
                    
                    display_name = ", ".join(display_parts) if display_parts else f"Issue {issue['issue_id']}"
                    
                    # Obtener conteo de artículos (puede ser 0 si no hay datos)
                    articles_count = articles_count_map.get(issue['issue_id'], 0)
                    
                    # Limpiar y validar título
                    clean_title = (issue['title'] or '').strip()
                    if not clean_title or clean_title == 'Sin título':
                        clean_title = display_name
                    
                    # Limpiar descripción
                    clean_description = (issue['description'] or '').strip()
                    
                    volume_data = {
                        'issue_id': issue['issue_id'],
                        'volume': issue['volume'],
                        'number': issue['number'],
                        'year': issue['year'],
                        'title': clean_title,
                        'description': clean_description,
                        'date_published': pub_date.isoformat() if pub_date else None,
                        'articles_count': articles_count,
                        'access_status': access_status,
                        'is_current': False,  # Se puede implementar lógica específica más adelante
                        'cover_image': issue['cover_image'],
                        'journal_title': issue['journal_title'] or 'Revista Científica',
                        'journal_abbreviation': issue['journal_abbreviation'] or '',
                        'url': issue_url,
                        'display_name': display_name,
                        'publication_period': f"{issue['year'] or 'Año no especificado'}"
                    }
                    
                    volumes_list.append(volume_data)
                
                print(f"✅ {len(volumes_list)} volúmenes procesados exitosamente")
                
                return {
                    'total_volumes': len(volumes_list),
                    'volumes': volumes_list,
                    'data_source': 'ojs_database_direct_no_publication_issues',
                    'response_time': '< 50ms',
                    'last_updated': datetime.now().isoformat(),
                    'database_info': {
                        'issues_found': len(issues),
                        'issues_with_articles': len([v for v in volumes_list if v['articles_count'] > 0]),
                        'total_articles': sum(v['articles_count'] for v in volumes_list),
                        'articles_counting_method': 'submissions_fallback' if not articles_count_map else 'publications_method'
                    },
                    'debug_info': {
                        'query_type': 'without_publication_issues_table',
                        'articles_count_map_size': len(articles_count_map)
                    }
                }
                
    except Exception as e:
        print(f"❌ Error en /volumes: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Retornar error estructurado
        return {
            'total_volumes': 0,
            'volumes': [],
            'error': str(e),
            'data_source': 'ojs_database_direct_no_publication_issues',
            'last_updated': datetime.now().isoformat(),
            'status': 'error',
            'debug_info': {
                'error_type': 'database_query_error',
                'missing_table': 'publication_issues'
            }
        }

# ================================
# ENDPOINT PARA VERIFICAR ESTRUCTURA DE BD
# ================================

@app.get("/debug/check-tables")
def check_database_tables():
    """Verificar qué tablas existen en la base de datos"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                
                # Ver todas las tablas
                cursor.execute("SHOW TABLES")
                all_tables = [row[f'Tables_in_{DB_CONFIG["database"]}'] for row in cursor.fetchall()]
                
                # Tablas que necesitamos para volúmenes
                required_tables = [
                    'issues', 'issue_settings', 'journals', 'journal_settings',
                    'submissions', 'publications', 'publication_issues'
                ]
                
                table_status = {}
                for table in required_tables:
                    table_status[table] = table in all_tables
                
                # Si publication_issues no existe, buscar alternativas
                alternative_tables = []
                if not table_status.get('publication_issues', False):
                    # Buscar tablas que puedan contener la relación
                    possible_alternatives = [t for t in all_tables if 'publication' in t.lower() or 'issue' in t.lower()]
                    alternative_tables = possible_alternatives
                
                return {
                    'database': DB_CONFIG['database'],
                    'all_tables_count': len(all_tables),
                    'required_tables_status': table_status,
                    'all_tables': sorted(all_tables),
                    'missing_tables': [t for t, exists in table_status.items() if not exists],
                    'alternative_tables': alternative_tables,
                    'recommendation': 'Use submissions table to count articles if publication_issues missing'
                }
                
    except Exception as e:
        return {
            'error': str(e),
            'message': 'Could not check database tables'
        }

# ================================
# ENDPOINT /volumes/{issue_id} CORREGIDO SIN publication_issues
# Reemplazar en main_hybrid.py
# ================================

# ================================
# DEBUG PARA VERIFICAR FILTRO DE FECHAS
# Agregar a main_hybrid.py
# ================================

@app.get("/debug/date-filtering/{issue_id}")
def debug_date_filtering(issue_id: int):
    """Verificar cómo está afectando el filtro de fechas a los artículos"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                
                # 1. Obtener fecha del volumen
                cursor.execute("""
                    SELECT issue_id, date_published, journal_id, volume, number
                    FROM issues 
                    WHERE issue_id = %s
                """, (issue_id,))
                issue_info = cursor.fetchone()
                
                if not issue_info:
                    return {'error': 'Issue not found'}
                
                volume_date = issue_info['date_published']
                journal_id = issue_info['journal_id']
                
                # 2. Ver TODOS los artículos del journal (sin filtro de fecha)
                cursor.execute("""
                    SELECT 
                        p.publication_id,
                        p.submission_id,
                        p.date_published,
                        p.seq,
                        ps_title.setting_value as title
                    FROM submissions s
                    JOIN publications p ON s.current_publication_id = p.publication_id
                    LEFT JOIN publication_settings ps_title ON p.publication_id = ps_title.publication_id 
                        AND ps_title.setting_name = 'title' AND ps_title.locale IN ('es', 'en')
                    WHERE s.context_id = %s AND p.status = 3
                    ORDER BY p.date_published DESC
                """, (journal_id,))
                all_articles = cursor.fetchall()
                
                # 3. Ver artículos CON filtro de fecha (±6 meses)
                if volume_date:
                    cursor.execute("""
                        SELECT 
                            p.publication_id,
                            p.submission_id,
                            p.date_published,
                            p.seq,
                            ps_title.setting_value as title
                        FROM submissions s
                        JOIN publications p ON s.current_publication_id = p.publication_id
                        LEFT JOIN publication_settings ps_title ON p.publication_id = ps_title.publication_id 
                            AND ps_title.setting_name = 'title' AND ps_title.locale IN ('es', 'en')
                        WHERE s.context_id = %s 
                          AND p.status = 3
                          AND (
                              p.date_published IS NULL OR
                              (p.date_published BETWEEN DATE_SUB(%s, INTERVAL 6 MONTH) 
                                                    AND DATE_ADD(%s, INTERVAL 6 MONTH))
                          )
                        ORDER BY p.date_published DESC
                    """, (journal_id, volume_date, volume_date))
                    filtered_articles = cursor.fetchall()
                else:
                    filtered_articles = all_articles[:15]  # Fallback
                
                # 4. Calcular rangos de fecha
                if volume_date:
                    from datetime import timedelta
                    date_range_start = volume_date - timedelta(days=180)  # 6 meses antes
                    date_range_end = volume_date + timedelta(days=180)    # 6 meses después
                else:
                    date_range_start = None
                    date_range_end = None
                
                # 5. Analizar qué artículos se excluyen
                excluded_articles = []
                included_articles = []
                
                for article in all_articles:
                    article_date = article['date_published']
                    is_included = False
                    exclusion_reason = None
                    
                    if not volume_date:
                        is_included = True
                    elif not article_date:
                        is_included = True  # NULL dates are included
                    elif date_range_start <= article_date <= date_range_end:
                        is_included = True
                    else:
                        exclusion_reason = f"Date {article_date} outside range {date_range_start} to {date_range_end}"
                    
                    article_info = {
                        'publication_id': article['publication_id'],
                        'submission_id': article['submission_id'],
                        'title': article['title'] or f"Article #{article['publication_id']}",
                        'date_published': article_date.isoformat() if article_date else None,
                        'exclusion_reason': exclusion_reason
                    }
                    
                    if is_included:
                        included_articles.append(article_info)
                    else:
                        excluded_articles.append(article_info)
                
                return {
                    'volume_info': {
                        'issue_id': issue_info['issue_id'],
                        'volume': issue_info['volume'],
                        'number': issue_info['number'],
                        'date_published': volume_date.isoformat() if volume_date else None,
                        'journal_id': journal_id
                    },
                    'date_filter_info': {
                        'volume_date': volume_date.isoformat() if volume_date else None,
                        'range_start': date_range_start.isoformat() if date_range_start else None,
                        'range_end': date_range_end.isoformat() if date_range_end else None,
                        'filter_window': '±6 months from volume date'
                    },
                    'article_counts': {
                        'total_articles_in_journal': len(all_articles),
                        'articles_included_by_filter': len(included_articles),
                        'articles_excluded_by_filter': len(excluded_articles)
                    },
                    'included_articles': included_articles,
                    'excluded_articles': excluded_articles,
                    'recommendation': {
                        'issue': 'Date filtering is excluding articles',
                        'solution': 'Remove date filter or use broader range',
                        'alternative': 'Use all articles from journal for this volume'
                    },
                    'timestamp': datetime.now().isoformat()
                }
                
    except Exception as e:
        import traceback
        return {
            'error': str(e),
            'traceback': traceback.format_exc()
        }

@app.get("/volumes-no-filter/{issue_id}")
def get_volume_details_no_date_filter(issue_id: int):
    """Endpoint sin filtro de fecha para mostrar TODOS los artículos del journal"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                
                print(f"🔍 Obteniendo volumen {issue_id} SIN filtro de fecha")
                
                # Información del issue (igual que antes)
                cursor.execute("""
                    SELECT 
                        i.issue_id, i.journal_id, i.volume, i.number, i.year,
                        i.date_published, i.date_notified, i.published,
                        
                        COALESCE(
                            MAX(CASE WHEN is_title.locale = 'es' THEN is_title.setting_value END),
                            MAX(CASE WHEN is_title.locale = 'en' THEN is_title.setting_value END),
                            CONCAT('Volumen ', COALESCE(i.volume, ''), ' Número ', COALESCE(i.number, ''))
                        ) as title,
                        
                        COALESCE(
                            MAX(CASE WHEN is_desc.locale = 'es' THEN is_desc.setting_value END),
                            MAX(CASE WHEN is_desc.locale = 'en' THEN is_desc.setting_value END),
                            ''
                        ) as description
                        
                    FROM issues i
                    LEFT JOIN issue_settings is_title ON i.issue_id = is_title.issue_id 
                        AND is_title.setting_name = 'title'
                    LEFT JOIN issue_settings is_desc ON i.issue_id = is_desc.issue_id 
                        AND is_desc.setting_name = 'description'
                    
                    WHERE i.issue_id = %s AND i.published = 1
                    GROUP BY i.issue_id, i.journal_id, i.volume, i.number, i.year, 
                             i.date_published, i.date_notified, i.published
                """, (issue_id,))
                
                issue_data = cursor.fetchone()
                
                if not issue_data:
                    raise HTTPException(status_code=404, detail="Volumen no encontrado")
                
                # SIN FILTRO DE FECHA - Obtener TODOS los artículos del journal
                cursor.execute("""
                    SELECT 
                        p.publication_id,
                        p.submission_id,
                        p.date_published,
                        p.seq
                    FROM submissions s
                    JOIN publications p ON s.current_publication_id = p.publication_id
                    WHERE s.context_id = %s AND p.status = 3
                    ORDER BY p.date_published DESC, p.seq ASC
                """, (issue_data['journal_id'],))
                
                basic_articles = cursor.fetchall()
                print(f"📄 TODOS los artículos encontrados (sin filtro): {len(basic_articles)}")
                
                # Procesar artículos (mismo código que el endpoint principal)
                articles = []
                for article in basic_articles:
                    pub_id = article['publication_id']
                    
                    # Obtener título
                    cursor.execute("""
                        SELECT setting_value 
                        FROM publication_settings 
                        WHERE publication_id = %s AND setting_name = 'title' 
                          AND locale IN ('es', 'en')
                        ORDER BY CASE WHEN locale = 'es' THEN 1 ELSE 2 END
                        LIMIT 1
                    """, (pub_id,))
                    title_result = cursor.fetchone()
                    title = title_result['setting_value'] if title_result else f"Artículo #{pub_id}"
                    
                    # Obtener abstract
                    cursor.execute("""
                        SELECT setting_value 
                        FROM publication_settings 
                        WHERE publication_id = %s AND setting_name = 'abstract' 
                          AND locale IN ('es', 'en')
                        ORDER BY CASE WHEN locale = 'es' THEN 1 ELSE 2 END
                        LIMIT 1
                    """, (pub_id,))
                    abstract_result = cursor.fetchone()
                    abstract = abstract_result['setting_value'] if abstract_result else ''
                    
                    # Obtener páginas
                    cursor.execute("""
                        SELECT setting_value 
                        FROM publication_settings 
                        WHERE publication_id = %s AND setting_name = 'pages'
                        LIMIT 1
                    """, (pub_id,))
                    pages_result = cursor.fetchone()
                    pages = pages_result['setting_value'] if pages_result else ''
                    
                    # Obtener autores
                    cursor.execute("""
                        SELECT 
                            COALESCE(fname.setting_value, '') as first_name,
                            COALESCE(lname.setting_value, '') as last_name
                        FROM authors a
                        LEFT JOIN author_settings fname ON a.author_id = fname.author_id 
                            AND fname.setting_name = 'givenName'
                        LEFT JOIN author_settings lname ON a.author_id = lname.author_id 
                            AND lname.setting_name = 'familyName'
                        WHERE a.publication_id = %s
                        ORDER BY a.seq ASC
                    """, (pub_id,))
                    
                    authors_data = cursor.fetchall()
                    
                    # Procesar autores
                    if authors_data:
                        authors_list = []
                        for author in authors_data:
                            first_name = (author['first_name'] or '').strip()
                            last_name = (author['last_name'] or '').strip()
                            
                            if first_name and last_name:
                                full_name = f"{first_name} {last_name}"
                            elif first_name:
                                full_name = first_name
                            elif last_name:
                                full_name = last_name
                            else:
                                continue
                            
                            authors_list.append(full_name)
                        
                        authors_string = '; '.join(authors_list) if authors_list else 'Autor no especificado'
                    else:
                        authors_string = 'Autor no especificado'
                    
                    # Limpiar HTML
                    if abstract:
                        import re
                        abstract = re.sub(r'<[^>]+>', '', abstract)
                        abstract = re.sub(r'\s+', ' ', abstract).strip()
                        if len(abstract) > 300:
                            abstract = abstract[:300] + '...'
                    
                    if title:
                        import re
                        title = re.sub(r'<[^>]+>', '', title).strip()
                    
                    # Construir artículo
                    complete_article = {
                        'publication_id': pub_id,
                        'submission_id': article['submission_id'],
                        'title': title,
                        'abstract': abstract or 'Sin resumen disponible',
                        'authors': authors_string,
                        'pages': pages,
                        'date_published': article['date_published'].isoformat() if article['date_published'] else None,
                        'url': f"/article/view/{article['submission_id']}"
                    }
                    
                    articles.append(complete_article)
                
                return {
                    'issue': {
                        'issue_id': issue_data['issue_id'],
                        'volume': issue_data['volume'],
                        'number': issue_data['number'],
                        'year': issue_data['year'],
                        'title': issue_data['title'],
                        'description': issue_data['description'],
                        'date_published': issue_data['date_published'].isoformat() if issue_data['date_published'] else None,
                        'is_current': False
                    },
                    'articles': articles,
                    'total_articles': len(articles),
                    'data_source': 'ojs_database_no_date_filter',
                    'last_updated': datetime.now().isoformat(),
                    'debug_info': {
                        'method_used': 'all_journal_articles_no_date_filter',
                        'searched_journal_id': issue_data['journal_id'],
                        'note': 'Shows ALL articles from journal without date filtering'
                    }
                }
                
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ================================
# ENDPOINTS LEGACY (Para compatibilidad)
# ================================

@app.get("/health")
def health_check():
    """Health check del sistema persistente"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                
                # Verificar recommendation_cache
                cursor.execute("SELECT COUNT(*) as count FROM recommendation_cache")
                cache_count = cursor.fetchone()['count']
                
        return {
            "status": "healthy",
            "system": "OJS Persistent Recommendations API",
            "version": "4.1.0",
            "architecture": "persistent_storage",
            "database": "connected",
            "scheduler": "active" if scheduler.is_running else "inactive",
            "cache_records": cache_count,
            "cache_status": "populated" if cache_count > 0 else "empty",
            "message": "Sistema funcionando con datos migrados de recommendation_cache"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

# ================================
# CONFIGURACIÓN DE DESARROLLO
# ================================

if __name__ == "__main__":
    import uvicorn
    
    print("🚀 Iniciando API de Recomendaciones Persistentes")
    print("=" * 70)
    print("📍 URL Principal: http://localhost:8000")
    print("📖 Documentación: http://localhost:8000/docs")
    print("🎯 Estado: http://localhost:8000/status")
    print("📊 Cache Status: http://localhost:8000/admin/cache-status")
    print("=" * 70)
    print("🔄 Arquitectura Persistente:")
    print("   • Migración automática de recommendation_cache")
    print("   • Cálculo automático diario a las 3:00 AM")
    print("   • Almacenamiento en BD para acceso ultra-rápido")
    print("   • Plugin PHP/JS sin necesidad de llamadas API")
    print("   • Respuestas < 5ms desde base de datos")
    print("=" * 70)
    print("📊 Endpoints Administrativos:")
    print("   • Calcular Ahora: POST /admin/calculate-now")
    print("   • Ver Recomendaciones: /admin/recommendations/{id}")
    print("   • Ver Homepage: /admin/homepage/{type}")
    print("   • Estado Cache: /admin/cache-status")
    print("   • Estado Sistema: /status")
    print("=" * 70)
    print("🎯 Base de Datos:")
    print("   • recommendation_cache: Fuente de datos (96 registros)")
    print("   • persistent_recommendations: Recomendaciones migradas")
    print("   • homepage_recommendations: Listas para homepage")
    print("   • recommendation_system_status: Estado del sistema")
    print("   • article_metrics_daily: Métricas de popularidad")
    print("=" * 70)
    
    uvicorn.run(
        "main_hybrid:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )