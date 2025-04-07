#!/usr/bin/env python3
"""
Schema Analyzer and Best Practices Reporter

This module analyzes relational schemas, evaluates them against Cassandra best practices,
and generates detailed PDF reports with recommendations for optimization.
"""

import json
import argparse
import os
import re
from collections import defaultdict, Counter
import networkx as nx
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, ListFlowable, ListItem
from reportlab.graphics.shapes import Drawing, Line
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.lib.units import inch

class SchemaAnalyzer:
    def __init__(self):
        self.schema = None
        self.tables = []
        self.relationships = []
        self.access_patterns = []
        self.analysis_results = {}
        self.recommendations = []
        self.best_practices_score = {}
        
    def load_schema(self, schema_file):
        """Load a schema from a JSON file."""
        try:
            with open(schema_file, 'r') as f:
                self.schema = json.load(f)
                self.tables = self.schema.get('tables', [])
                return True
        except Exception as e:
            print(f"Error loading schema: {e}")
            return False

    def load_queries(self, queries_file):
        """Load query patterns from a file."""
        if not os.path.exists(queries_file):
            print(f"Queries file {queries_file} not found.")
            return False
            
        try:
            with open(queries_file, 'r') as f:
                query_lines = f.readlines()
                
            for line in query_lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    self.access_patterns.append(line)
            
            return True
        except Exception as e:
            print(f"Error loading queries: {e}")
            return False

    def analyze_schema(self):
        """Perform complete schema analysis."""
        if not self.schema:
            return False
            
        # Build analysis data structure
        self.analyze_table_structure()
        self.analyze_relationships()
        self.analyze_access_patterns()
        self.evaluate_against_best_practices()
        self.generate_recommendations()
        
        return True

    def analyze_table_structure(self):
        """Analyze the structure of tables."""
        table_stats = {}
        all_column_types = Counter()
        
        for table in self.tables:
            table_name = table['name']
            columns = table.get('columns', [])
            foreign_keys = table.get('foreign_keys', [])
            
            # Count column data types
            column_types = Counter()
            for col in columns:
                col_type = col.get('type', '').lower().split('(')[0]
                column_types[col_type] += 1
                all_column_types[col_type] += 1
            
            # Analyze primary key
            primary_key_cols = [c['name'] for c in columns if c.get('primary_key', False)]
            
            # Check for problematic types for Cassandra
            problematic_types = []
            for col in columns:
                col_type = col.get('type', '').lower()
                if 'float' in col_type or 'real' in col_type:
                    problematic_types.append((col['name'], col_type, 'Floating-point types can cause precision issues'))
                elif 'decimal' in col_type:
                    problematic_types.append((col['name'], col_type, 'Consider using bigint with scaled integers instead'))
            
            table_stats[table_name] = {
                'columns_count': len(columns),
                'primary_key': primary_key_cols,
                'foreign_keys_count': len(foreign_keys),
                'column_types': dict(column_types),
                'nullable_columns': sum(1 for c in columns if c.get('nullable', True)),
                'problematic_types': problematic_types
            }
        
        self.analysis_results['table_structure'] = {
            'table_stats': table_stats,
            'total_tables': len(self.tables),
            'total_columns': sum(t['columns_count'] for t in table_stats.values()),
            'data_types_distribution': dict(all_column_types)
        }
        
    def analyze_relationships(self):
        """Analyze relationships between tables."""
        # Create a graph to represent table relationships
        graph = nx.DiGraph()
        
        # Add tables as nodes
        for table in self.tables:
            graph.add_node(table['name'])
        
        # Add relationships as edges
        for table in self.tables:
            for fk in table.get('foreign_keys', []):
                ref_table = fk.get('references', {}).get('table')
                if ref_table:
                    graph.add_edge(table['name'], ref_table)
                    self.relationships.append({
                        'from_table': table['name'],
                        'from_column': fk.get('column'),
                        'to_table': ref_table,
                        'to_column': fk.get('references', {}).get('column')
                    })
        
        # Find tables with high connectivity
        high_connectivity_tables = []
        for node in graph.nodes():
            in_degree = graph.in_degree(node)
            out_degree = graph.out_degree(node)
            if in_degree + out_degree > 3:  # Arbitrary threshold for "high connectivity"
                high_connectivity_tables.append({
                    'table': node,
                    'in_references': in_degree,
                    'out_references': out_degree,
                    'total_connections': in_degree + out_degree
                })
        
        # Identify relationship patterns
        one_to_many = []
        many_to_many = []
        self_references = []
        
        for table in self.tables:
            # Check for junction tables (potential many-to-many)
            if len(table.get('foreign_keys', [])) >= 2 and len(table.get('columns', [])) <= 4:
                referenced_tables = []
                for fk in table.get('foreign_keys', []):
                    ref_table = fk.get('references', {}).get('table')
                    if ref_table:
                        referenced_tables.append(ref_table)
                
                if len(referenced_tables) >= 2:
                    many_to_many.append({
                        'junction_table': table['name'],
                        'connected_tables': referenced_tables
                    })
            
            # Check for self-references (hierarchical data)
            for fk in table.get('foreign_keys', []):
                ref_table = fk.get('references', {}).get('table')
                if ref_table == table['name']:
                    self_references.append({
                        'table': table['name'],
                        'column': fk.get('column')
                    })
        
        # Identify one-to-many relationships (most common FK relationships)
        for rel in self.relationships:
            if (rel['from_table'], rel['to_table']) not in [(m['junction_table'], t) for m in many_to_many for t in m['connected_tables']]:
                one_to_many.append(rel)
        
        # Build relationship chains
        chains = []
        for node in graph.nodes():
            paths = []
            for target in graph.nodes():
                if node != target:
                    # Find all paths between the two nodes
                    try:
                        all_paths = list(nx.all_simple_paths(graph, node, target, cutoff=3))
                        paths.extend(all_paths)
                    except:
                        pass
            
            # Keep only the longest chains
            if paths:
                max_len = max(len(p) for p in paths)
                longest_paths = [p for p in paths if len(p) >= max_len]
                for path in longest_paths:
                    if len(path) > 2:  # Only consider chains of 3+ tables
                        chains.append(path)
        
        self.analysis_results['relationships'] = {
            'total_relationships': len(self.relationships),
            'high_connectivity_tables': high_connectivity_tables,
            'one_to_many': one_to_many,
            'many_to_many': many_to_many,
            'self_references': self_references,
            'relationship_chains': chains
        }

    def analyze_access_patterns(self):
        """Analyze query access patterns."""
        if not self.access_patterns:
            self.analysis_results['access_patterns'] = {
                'no_queries_provided': True
            }
            return
            
        join_patterns = []
        where_conditions = []
        order_by_columns = []
        tables_in_queries = Counter()
        
        for query in self.access_patterns:
            # Extract tables in the query
            tables = self._extract_tables_from_query(query)
            for table in tables:
                tables_in_queries[table] += 1
                
            # Analyze joins
            if len(tables) > 1:
                join_patterns.append({
                    'tables': tables,
                    'query': query
                })
                
            # Analyze WHERE conditions
            conditions = self._extract_conditions_from_query(query)
            if conditions:
                where_conditions.extend(conditions)
                
            # Analyze ORDER BY
            ordering = self._extract_ordering_from_query(query)
            if ordering:
                order_by_columns.extend(ordering)
                
        # Summarize results
        most_queried_tables = tables_in_queries.most_common(5)
        most_common_where = Counter(where_conditions).most_common(5)
        most_common_ordering = Counter(order_by_columns).most_common(5)
        
        self.analysis_results['access_patterns'] = {
            'total_queries': len(self.access_patterns),
            'most_queried_tables': most_queried_tables,
            'join_patterns': join_patterns,
            'most_common_where': most_common_where,
            'most_common_ordering': most_common_ordering
        }

    def _extract_tables_from_query(self, query):
        """Extract table names from a SQL query."""
        # Simple regex to find tables in FROM and JOIN clauses
        from_pattern = re.compile(r'from\s+([a-zA-Z0-9_]+)', re.IGNORECASE)
        join_pattern = re.compile(r'join\s+([a-zA-Z0-9_]+)', re.IGNORECASE)
        
        tables = []
        from_matches = from_pattern.findall(query)
        join_matches = join_pattern.findall(query)
        
        if from_matches:
            tables.extend(from_matches)
        if join_matches:
            tables.extend(join_matches)
            
        return tables
    
    def _extract_conditions_from_query(self, query):
        """Extract WHERE conditions from a SQL query."""
        # Simple regex to find conditions in WHERE clause
        where_pattern = re.compile(r'where\s+(.*?)(?:order by|group by|limit|$)', re.IGNORECASE | re.DOTALL)
        condition_pattern = re.compile(r'([a-zA-Z0-9_.]+)\s*(?:=|>|<|>=|<=|!=|LIKE|IN)\s*')
        
        conditions = []
        where_matches = where_pattern.findall(query)
        
        if where_matches:
            where_clause = where_matches[0].strip()
            condition_matches = condition_pattern.findall(where_clause)
            conditions = [col.split('.')[-1] if '.' in col else col for col in condition_matches]
            
        return conditions
    
    def _extract_ordering_from_query(self, query):
        """Extract ORDER BY columns from a SQL query."""
        # Simple regex to find ordering columns
        order_pattern = re.compile(r'order by\s+(.*?)(?:limit|$)', re.IGNORECASE | re.DOTALL)
        
        ordering = []
        order_matches = order_pattern.findall(query)
        
        if order_matches:
            order_clause = order_matches[0].strip()
            # Split by commas and extract column names
            for item in order_clause.split(','):
                col = item.strip().split()[0]  # Get just the column name, not ASC/DESC
                ordering.append(col.split('.')[-1] if '.' in col else col)
            
        return ordering

    def evaluate_against_best_practices(self):
        """Evaluate the schema against Cassandra best practices."""
        best_practices = {}
        
        # 1. Evaluate primary key composition
        pk_scores = []
        for table_name, stats in self.analysis_results['table_structure']['table_stats'].items():
            pk = stats['primary_key']
            score = 0
            issues = []
            
            if not pk:
                score = 0
                issues.append("No primary key defined")
            elif len(pk) == 1:
                # Check if this is a UUID or other high-cardinality field
                col_type = next((c.get('type', '').lower() for c in self._get_table_columns(table_name) if c['name'] == pk[0]), "")
                if 'uuid' in col_type or 'id' in pk[0].lower():
                    score = 80
                    issues.append("Single-column primary key is OK but could be improved with composite keys")
                else:
                    score = 50
                    issues.append("Single-column primary key may lead to hotspots if not high-cardinality")
            else:
                # Composite key
                score = 100
                issues.append("Good: Composite primary key")
            
            pk_scores.append({
                'table': table_name,
                'score': score,
                'issues': issues
            })
        
        avg_pk_score = sum(s['score'] for s in pk_scores) / len(pk_scores) if pk_scores else 0
        best_practices['primary_keys'] = {
            'score': avg_pk_score,
            'details': pk_scores
        }
        
        # 2. Evaluate data types
        dt_scores = []
        for table_name, stats in self.analysis_results['table_structure']['table_stats'].items():
            problematic = stats['problematic_types']
            score = 100 - (len(problematic) * 20)  # Deduct 20 points per problematic type
            score = max(0, score)  # Ensure non-negative
            
            dt_scores.append({
                'table': table_name,
                'score': score,
                'issues': [f"{p[0]} ({p[1]}): {p[2]}" for p in problematic] if problematic else ["No data type issues"]
            })
        
        avg_dt_score = sum(s['score'] for s in dt_scores) / len(dt_scores) if dt_scores else 0
        best_practices['data_types'] = {
            'score': avg_dt_score,
            'details': dt_scores
        }
        
        # 3. Evaluate denormalization potential
        denorm_scores = []
        max_chains = 5  # Arbitrary cap on relationship chains
        
        # Check join patterns from queries
        if 'access_patterns' in self.analysis_results and not self.analysis_results['access_patterns'].get('no_queries_provided', False):
            join_patterns = self.analysis_results['access_patterns']['join_patterns']
            
            for table_name in [t['name'] for t in self.tables]:
                # Count joins involving this table
                joins_count = sum(1 for j in join_patterns if table_name in j['tables'])
                
                # Calculate score - higher joins means more denormalization needed
                if joins_count == 0:
                    score = 100  # No joins needed
                    issues = ["Table not involved in joins, no denormalization needed"]
                else:
                    # More joins = lower score = more denormalization needed
                    score = max(0, 100 - (joins_count * 15))
                    issues = [f"Table involved in {joins_count} join patterns, consider denormalization"]
                    
                    # Suggest specific denormalizations
                    for jp in join_patterns:
                        if table_name in jp['tables']:
                            other_tables = [t for t in jp['tables'] if t != table_name]
                            if other_tables:
                                issues.append(f"Consider denormalizing data from {', '.join(other_tables)} into {table_name}")
                
                denorm_scores.append({
                    'table': table_name,
                    'score': score,
                    'issues': issues
                })
        else:
            # If no queries provided, base on table relationships
            chains = self.analysis_results['relationships']['relationship_chains']
            one_to_many = self.analysis_results['relationships']['one_to_many']
            many_to_many = self.analysis_results['relationships']['many_to_many']
            
            for table_name in [t['name'] for t in self.tables]:
                issues = []
                
                # Check if table is in relationship chains
                table_chains = [c for c in chains if table_name in c]
                chain_count = min(len(table_chains), max_chains)
                
                # Check one-to-many relationships
                o2m_count = sum(1 for r in one_to_many if r['from_table'] == table_name or r['to_table'] == table_name)
                
                # Check many-to-many relationships
                m2m_count = sum(1 for m in many_to_many if m['junction_table'] == table_name or table_name in m['connected_tables'])
                
                # Calculate score - more relationships = more denormalization needed
                relationship_factor = chain_count + o2m_count + m2m_count
                score = max(0, 100 - (relationship_factor * 10))
                
                if relationship_factor == 0:
                    issues.append("Table has no relationships, no denormalization needed")
                else:
                    if chain_count:
                        chain_tables = [c for chain in table_chains for c in chain if c != table_name]
                        issues.append(f"Table part of {chain_count} relationship chains with {', '.join(set(chain_tables))}")
                    
                    if o2m_count:
                        o2m_tables = []
                        for r in one_to_many:
                            if r['from_table'] == table_name:
                                o2m_tables.append(r['to_table'])
                            elif r['to_table'] == table_name:
                                o2m_tables.append(r['from_table'])
                        issues.append(f"Table has one-to-many relationships with {', '.join(set(o2m_tables))}")
                    
                    if m2m_count:
                        m2m_tables = []
                        for m in many_to_many:
                            if m['junction_table'] == table_name:
                                m2m_tables.extend(m['connected_tables'])
                            elif table_name in m['connected_tables']:
                                m2m_tables.append(m['junction_table'])
                                other_end = [t for t in m['connected_tables'] if t != table_name]
                                m2m_tables.extend(other_end)
                        issues.append(f"Table involved in many-to-many relationships with {', '.join(set(m2m_tables))}")
                
                denorm_scores.append({
                    'table': table_name,
                    'score': score,
                    'issues': issues
                })
        
        avg_denorm_score = sum(s['score'] for s in denorm_scores) / len(denorm_scores) if denorm_scores else 0
        best_practices['denormalization'] = {
            'score': avg_denorm_score,
            'details': denorm_scores
        }
        
        # 4. Evaluate query pattern alignment
        query_scores = []
        
        if 'access_patterns' in self.analysis_results and not self.analysis_results['access_patterns'].get('no_queries_provided', False):
            most_queried = dict(self.analysis_results['access_patterns']['most_queried_tables'])
            most_where = dict(self.analysis_results['access_patterns']['most_common_where'])
            most_order = dict(self.analysis_results['access_patterns']['most_common_ordering'])
            
            for table_name in [t['name'] for t in self.tables]:
                issues = []
                
                # Get primary key for this table
                pk = self.analysis_results['table_structure']['table_stats'][table_name]['primary_key']
                
                # Check if primary key columns are used in WHERE clauses
                pk_in_where = sum(1 for p in pk if p in most_where)
                
                # Check if non-primary key columns are used in WHERE clauses
                columns = [c['name'] for c in self._get_table_columns(table_name)]
                non_pk_cols = [c for c in columns if c not in pk]
                non_pk_in_where = sum(1 for c in non_pk_cols if c in most_where)
                
                # Check if columns are used in ORDER BY
                pk_in_order = sum(1 for p in pk if p in most_order)
                non_pk_in_order = sum(1 for c in non_pk_cols if c in most_order)
                
                # Calculate alignment score
                query_count = most_queried.get(table_name, 0)
                
                if query_count == 0:
                    score = 50  # Neutral if not queried
                    issues.append("Table not found in query patterns")
                else:
                    # Base score on alignment of primary key with query patterns
                    base_score = 50
                    
                    # Bonus for PK used in WHERE clauses
                    if pk_in_where > 0:
                        base_score += 20
                        issues.append(f"Good: Primary key column(s) used in WHERE conditions")
                    else:
                        base_score -= 20
                        issues.append(f"Issue: Primary key not used in WHERE conditions")
                    
                    # Penalty for non-PK used in WHERE extensively
                    if non_pk_in_where > 2:
                        base_score -= 15
                        issues.append(f"Issue: Multiple non-primary key columns used in WHERE conditions")
                    
                    # Handle ORDER BY
                    if pk_in_order > 0:
                        base_score += 10
                        issues.append(f"Good: Primary key column(s) used in ORDER BY")
                    elif non_pk_in_order > 0:
                        base_score -= 10
                        issues.append(f"Issue: Non-primary key columns used in ORDER BY")
                    
                    score = max(0, min(100, base_score))
                
                query_scores.append({
                    'table': table_name,
                    'score': score,
                    'issues': issues
                })
        else:
            # If no queries provided, give neutral scores
            for table_name in [t['name'] for t in self.tables]:
                query_scores.append({
                    'table': table_name,
                    'score': 50,
                    'issues': ["No query patterns provided to evaluate"]
                })
        
        avg_query_score = sum(s['score'] for s in query_scores) / len(query_scores) if query_scores else 0
        best_practices['query_patterns'] = {
            'score': avg_query_score,
            'details': query_scores
        }
        
        # Calculate overall score
        weights = {
            'primary_keys': 0.3,
            'data_types': 0.2,
            'denormalization': 0.25,
            'query_patterns': 0.25
        }
        
        overall_score = sum(best_practices[k]['score'] * weights[k] for k in weights)
        
        self.best_practices_score = {
            'overall': overall_score,
            'categories': best_practices
        }

    def generate_recommendations(self):
        """Generate recommendations based on analysis."""
        recommendations = []
        
        # 1. Primary Key Recommendations
        low_pk_tables = [d for d in self.best_practices_score['categories']['primary_keys']['details'] if d['score'] < 70]
        if low_pk_tables:
            for table in low_pk_tables:
                recommendations.append({
                    'category': 'Primary Keys',
                    'table': table['table'],
                    'recommendation': f"Improve primary key design for table '{table['table']}'",
                    'details': "; ".join(table['issues']),
                    'suggested_fix': self._generate_pk_suggestion(table['table'])
                })
        
        # 2. Data Type Recommendations
        problematic_types = []
        for table_name, stats in self.analysis_results['table_structure']['table_stats'].items():
            for col_name, col_type, issue in stats['problematic_types']:
                problematic_types.append({
                    'category': 'Data Types',
                    'table': table_name,
                    'column': col_name,
                    'recommendation': f"Replace {col_type} with a more Cassandra-friendly type",
                    'details': issue,
                    'suggested_fix': self._generate_type_suggestion(col_type)
                })
        
        recommendations.extend(problematic_types)
        
        # 3. Denormalization Recommendations
        # Focus on tables involved in most queries with joins
        if 'access_patterns' in self.analysis_results and not self.analysis_results['access_patterns'].get('no_queries_provided', False):
            join_patterns = self.analysis_results['access_patterns']['join_patterns']
            
            # Count tables in joins
            tables_in_joins = Counter()
            for jp in join_patterns:
                for table in jp['tables']:
                    tables_in_joins[table] += 1
            
            # Recommend denormalization for frequently joined tables
            for table, count in tables_in_joins.most_common(5):
                if count >= 2:  # Arbitrary threshold
                    joined_with = []
                    for jp in join_patterns:
                        if table in jp['tables']:
                            for other in jp['tables']:
                                if other != table:
                                    joined_with.append(other)
                    
                    if joined_with:
                        top_joins = Counter(joined_with).most_common(3)
                        recommendations.append({
                            'category': 'Denormalization',
                            'table': table,
                            'recommendation': f"Denormalize data from related tables into '{table}'",
                            'details': f"Table '{table}' is joined with {', '.join([f'{t} ({c} times)' for t, c in top_joins])}",
                            'suggested_fix': self._generate_denorm_suggestion(table, [t for t, _ in top_joins])
                        })
        
        # 4. Query Pattern Recommendations
        if 'access_patterns' in self.analysis_results and not self.analysis_results['access_patterns'].get('no_queries_provided', False):
            # Identify tables with misaligned query patterns
            query_issues = [d for d in self.best_practices_score['categories']['query_patterns']['details'] if d['score'] < 60]
            
            for table in query_issues:
                table_name = table['table']
                # Get where conditions for this table's queries
                where_cols = []
                for query in self.access_patterns:
                    if table_name in self._extract_tables_from_query(query):
                        where_cols.extend(self._extract_conditions_from_query(query))
                
                if where_cols:
                    most_common = Counter(where_cols).most_common(3)
                    pk = self.analysis_results['table_structure']['table_stats'][table_name]['primary_key']
                    
                    # Check if WHERE columns match PK
                    misaligned = [col for col, _ in most_common if col not in pk]
                    if misaligned:
                        recommendations.append({
                            'category': 'Query Patterns',
                            'table': table_name,
                            'recommendation': f"Align table design with query patterns",
                            'details': f"Columns frequently used in WHERE clauses ({', '.join(misaligned)}) are not part of the primary key",
                            'suggested_fix': self._generate_query_suggestion(table_name, misaligned, pk)
                        })
        
        # 5. Many-to-Many Relationship Recommendations
        for m2m in self.analysis_results['relationships']['many_to_many']:
            recommendations.append({
                'category': 'Many-to-Many Relationships',
                'table': m2m['junction_table'],
                'recommendation': f"Replace junction table with duplicated data",
                'details': f"Junction table '{m2m['junction_table']}' connects {', '.join(m2m['connected_tables'])}",
                'suggested_fix': self._generate_m2m_suggestion(m2m['junction_table'], m2m['connected_tables'])
            })
        
        # 6. Self-Reference Recommendations
        for self_ref in self.analysis_results['relationships']['self_references']:
            recommendations.append({
                'category': 'Hierarchical Data',
                'table': self_ref['table'],
                'recommendation': f"Restructure hierarchical data",
                'details': f"Table '{self_ref['table']}' has a self-reference on column '{self_ref['column']}'",
                'suggested_fix': self._generate_hierarchy_suggestion(self_ref['table'], self_ref['column'])
            })
        
        self.recommendations = recommendations

    def _get_table_columns(self, table_name):
        """Get columns for a specific table."""
        for table in self.tables:
            if table['name'] == table_name:
                return table.get('columns', [])
        return []

    def _generate_pk_suggestion(self, table_name):
        """Generate suggestion for improving primary key."""
        columns = self._get_table_columns(table_name)
        pk = [c['name'] for c in columns if c.get('primary_key', False)]
        
        # If no primary key, suggest using UUID
        if not pk:
            return f"Add a UUID column as partition key, e.g., PRIMARY KEY (id, created_at)"
        
        # If single column PK, suggest adding a clustering column
        if len(pk) == 1:
            # Look for timestamp/date columns to use as clustering
            timestamp_cols = [c['name'] for c in columns if 'time' in c['type'].lower() or 'date' in c['type'].lower()]
            if timestamp_cols:
                return f"Use composite key with {pk[0]} as partition key and {timestamp_cols[0]} as clustering column: PRIMARY KEY(({pk[0]}), {timestamp_cols[0]})"
            else:
                return f"Add a timestamp column for clustering and use: PRIMARY KEY(({pk[0]}), timestamp_column)"
        
        return "Current primary key structure is suitable for Cassandra"
    
    def _generate_type_suggestion(self, col_type):
        """Generate suggestion for improving column data type."""
        col_type = col_type.lower()
        
        if 'float' in col_type or 'real' in col_type:
            return "Replace with 'decimal' or use scaled integers stored as 'bigint' for precise calculations"
        elif 'decimal' in col_type:
            # Extract precision and scale if available
            match = re.search(r'decimal\((\d+),(\d+)\)', col_type)
            if match:
                precision, scale = match.groups()
                multiplier = 10 ** int(scale)
                return f"Convert to 'bigint' and multiply values by {multiplier} to preserve precision"
            return "Convert to 'bigint' with appropriate scaling factor"
        elif 'datetime' in col_type:
            return "Use 'timestamp' type in Cassandra"
        elif 'varchar' in col_type or 'char' in col_type:
            return "Use 'text' type in Cassandra"
        elif 'enum' in col_type:
            return "Replace with 'text' type in Cassandra"
        elif 'json' in col_type:
            return "Use 'text' type and handle JSON serialization in application code"
        else:
            return f"Review if '{col_type}' has a direct Cassandra equivalent"

    def _generate_denorm_suggestion(self, main_table, related_tables):
        """Generate suggestion for denormalizing related tables."""
        if not related_tables:
            return "No specific denormalization needed"
            
        parts = []
        for rel_table in related_tables:
            # Get foreign keys between these tables
            rel_cols = []
            for rel in self.relationships:
                if (rel['from_table'] == main_table and rel['to_table'] == rel_table) or \
                   (rel['from_table'] == rel_table and rel['to_table'] == main_table):
                    rel_cols.append(rel)
            
            if rel_cols:
                # This is a one-to-many relationship
                if len(rel_cols) == 1:
                    rel = rel_cols[0]
                    if rel['from_table'] == main_table:
                        parts.append(f"Duplicate '{main_table}' data into '{rel_table}' to eliminate joins")
                    else:
                        # Get columns from related table
                        rel_columns = [c['name'] for c in self._get_table_columns(rel_table)]
                        non_key_cols = [c for c in rel_columns if c != rel['from_column']]
                        
                        if len(non_key_cols) <= 3:  # Arbitrary threshold for embedding vs. collection
                            cols_str = ', '.join(non_key_cols)
                            parts.append(f"Embed '{rel_table}' data (columns: {cols_str}) directly into '{main_table}'")
                        else:
                            parts.append(f"Use a collection (list, set, or map) in '{main_table}' to store related '{rel_table}' data")
            else:
                # Fallback for when relationship details aren't clear
                parts.append(f"Create a denormalized table combining '{main_table}' and '{rel_table}'")
                
        return "; ".join(parts)

    def _generate_query_suggestion(self, table_name, where_cols, pk):
        """Generate suggestion for aligning table with query patterns."""
        if not where_cols:
            return "No specific query pattern optimizations needed"
            
        # If we have WHERE columns not in PK, suggest changing PK
        non_pk_where = [c for c in where_cols if c not in pk]
        if non_pk_where:
            primary_where = non_pk_where[0]  # Most frequently used WHERE column
            
            if not pk:
                secondary_cols = non_pk_where[1:] if len(non_pk_where) > 1 else []
                if secondary_cols:
                    return f"Create a primary key using '{primary_where}' as partition key and {', '.join(secondary_cols)} as clustering columns"
                else:
                    return f"Create a primary key using '{primary_where}' as partition key"
            else:
                if len(pk) == 1:
                    return f"Consider a composite key with '{pk[0]}' and '{primary_where}' or create a secondary table with '{primary_where}' as partition key"
                else:
                    return f"Create a secondary table with '{primary_where}' as partition key to support this query pattern"
        else:
            return "Current primary key aligns with query patterns"

    def _generate_m2m_suggestion(self, junction_table, connected_tables):
        """Generate suggestion for handling many-to-many relationships."""
        if len(connected_tables) < 2:
            return "Not enough connected tables identified for many-to-many relationship"
            
        table1, table2 = connected_tables[:2]
        
        # Determine which side is "one" vs "many" based on query patterns
        if 'access_patterns' in self.analysis_results and not self.analysis_results['access_patterns'].get('no_queries_provided', False):
            # Look at WHERE conditions to guess which is the "one" side
            where_counts = {}
            for query in self.access_patterns:
                tables = self._extract_tables_from_query(query)
                if junction_table in tables and (table1 in tables or table2 in tables):
                    conditions = self._extract_conditions_from_query(query)
                    for condition in conditions:
                        where_counts[condition] = where_counts.get(condition, 0) + 1
            
            # Get foreign key columns
            fk_to_table1 = None
            fk_to_table2 = None
            for rel in self.relationships:
                if rel['from_table'] == junction_table:
                    if rel['to_table'] == table1:
                        fk_to_table1 = rel['from_column']
                    elif rel['to_table'] == table2:
                        fk_to_table2 = rel['from_column']
            
            # Check which foreign key is used more in WHERE
            if fk_to_table1 and fk_to_table2:
                if where_counts.get(fk_to_table1, 0) > where_counts.get(fk_to_table2, 0):
                    # table1 is queried more often
                    return f"Create a collection in '{table1}' to store related '{table2}' IDs and duplicate data from '{junction_table}'"
                else:
                    # table2 is queried more often
                    return f"Create a collection in '{table2}' to store related '{table1}' IDs and duplicate data from '{junction_table}'"
        
        # If no clear direction, suggest both options
        return f"Option 1: Create a collection in '{table1}' to store related '{table2}' IDs; Option 2: Create a collection in '{table2}' to store related '{table1}' IDs"

    def _generate_hierarchy_suggestion(self, table_name, self_ref_column):
        """Generate suggestion for handling hierarchical data."""
        return f"For hierarchical data in '{table_name}', consider: 1) Materialized paths: store the full path to each node; 2) Adjacency lists: store all children IDs in a collection; 3) Nested sets: store left/right indexes for efficient subtree queries"

    def generate_pdf_report(self, output_file):
        """Generate a PDF report with analysis results and recommendations."""
        if not self.analysis_results or not self.best_practices_score:
            print("No analysis results to report. Run analyze_schema() first.")
            return False
            
        try:
            doc = SimpleDocTemplate(output_file, pagesize=letter)
            styles = getSampleStyleSheet()
            elements = []
            
            # Add custom styles - CHECK FOR EXISTING STYLES FIRST
            custom_styles = {
                'Heading1': ParagraphStyle(name='Heading1', fontSize=18, spaceAfter=12),
                'Heading2': ParagraphStyle(name='Heading2', fontSize=14, spaceAfter=8, spaceBefore=12),
                'Heading3': ParagraphStyle(name='Heading3', fontSize=12, spaceAfter=6, spaceBefore=6),
                'TableHeader': ParagraphStyle(name='TableHeader', fontSize=10, alignment=1, textColor=colors.white, backColor=colors.darkblue),
                'Score': ParagraphStyle(name='Score', fontSize=16, spaceBefore=12, spaceAfter=12),
                'Note': ParagraphStyle(name='Note', fontName='Helvetica-Oblique', fontSize=10, textColor=colors.gray)
            }
            
            # Only add styles that don't already exist
            for style_name, style in custom_styles.items():
                if style_name not in styles:
                    styles.add(style)
                
            # Title
            elements.append(Paragraph("Cassandra Schema Optimization Report", styles['Heading1']))
            elements.append(Spacer(1, 12))
            
            # Overall Score
            overall_score = self.best_practices_score['overall']
            score_text = f"Overall Schema Score: {overall_score:.1f}/100"
            
            if overall_score >= 80:
                score_color = colors.green
                assessment = "EXCELLENT: This schema is well-suited for Cassandra with minor optimizations needed."
            elif overall_score >= 60:
                score_color = colors.orange
                assessment = "GOOD: This schema can work with Cassandra but needs moderate optimizations."
            else:
                score_color = colors.red
                assessment = "NEEDS WORK: Significant optimizations required for effective Cassandra implementation."
            
            elements.append(Paragraph(score_text, ParagraphStyle('Score', fontSize=16, textColor=score_color, spaceBefore=12, spaceAfter=12)))
            elements.append(Paragraph(assessment, styles['Normal']))
            elements.append(Spacer(1, 12))
            
            # Executive Summary
            elements.append(Paragraph("Executive Summary", styles['Heading2']))
            
            # Category scores
            categories = self.best_practices_score['categories']
            category_data = [["Category", "Score", "Assessment"]]
            for cat_name, cat_data in categories.items():
                score = cat_data['score']
                
                if score >= 80:
                    assessment = "Excellent"
                elif score >= 60:
                    assessment = "Good"
                elif score >= 40:
                    assessment = "Fair"
                else:
                    assessment = "Poor"
                
                category_data.append([cat_name.replace('_', ' ').title(), f"{score:.1f}/100", assessment])
            
            category_table = Table(category_data, colWidths=[200, 100, 100])
            category_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ALIGN', (1, 1), (1, -1), 'CENTER'),
                ('ALIGN', (2, 1), (2, -1), 'CENTER'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ]))
            elements.append(category_table)
            elements.append(Spacer(1, 12))
            
            # Generate score chart
            elements.append(self._create_score_chart())
            elements.append(Spacer(1, 12))
            
            # Schema Overview
            elements.append(Paragraph("Schema Overview", styles['Heading2']))
            
            # Table counts
            elements.append(Paragraph(f"Total Tables: {self.analysis_results['table_structure']['total_tables']}", styles['Normal']))
            elements.append(Paragraph(f"Total Columns: {self.analysis_results['table_structure']['total_columns']}", styles['Normal']))
            elements.append(Paragraph(f"Total Relationships: {self.analysis_results['relationships']['total_relationships']}", styles['Normal']))
            
            if 'access_patterns' in self.analysis_results and not self.analysis_results['access_patterns'].get('no_queries_provided', False):
                elements.append(Paragraph(f"Query Patterns Analyzed: {self.analysis_results['access_patterns']['total_queries']}", styles['Normal']))
            
            elements.append(Spacer(1, 12))
            
            # Top Recommendations
            elements.append(Paragraph("Top Recommendations", styles['Heading2']))
            
            # Group recommendations by category
            rec_by_category = defaultdict(list)
            for rec in self.recommendations:
                rec_by_category[rec['category']].append(rec)
            
            # Add top 3 recommendations from each category
            for category, recs in rec_by_category.items():
                elements.append(Paragraph(f"{category} Recommendations", styles['Heading3']))
                
                rec_items = []
                for i, rec in enumerate(recs[:3]):  # Limit to top 3
                    rec_text = f"<b>{rec['table']}:</b> {rec['recommendation']}<br/>{rec['details']}<br/><i>Suggested solution:</i> {rec['suggested_fix']}"
                    rec_items.append(ListItem(Paragraph(rec_text, styles['Normal'])))
                
                if rec_items:
                    elements.append(ListFlowable(rec_items, bulletType='bullet', leftIndent=20))
                else:
                    elements.append(Paragraph("No specific recommendations for this category.", styles['Normal']))
                
                elements.append(Spacer(1, 8))
            
            # Page break before detailed analysis
            elements.append(PageBreak())
            
            # Detailed Analysis
            elements.append(Paragraph("Detailed Schema Analysis", styles['Heading2']))
            
            # 1. Table Structure Analysis
            elements.append(Paragraph("Table Structure Analysis", styles['Heading3']))
            
            # Create table for problematic data types
            problem_tables = []
            for table_name, stats in self.analysis_results['table_structure']['table_stats'].items():
                problems = stats['problematic_types']
                if problems:
                    for col_name, col_type, issue in problems:
                        problem_tables.append([table_name, col_name, col_type, issue])
            
            if problem_tables:
                elements.append(Paragraph("Tables with Problematic Data Types for Cassandra:", styles['Normal']))
                
                problem_data = [["Table", "Column", "Current Type", "Issue"]]
                problem_data.extend(problem_tables)
                
                problem_table = Table(problem_data, colWidths=[100, 100, 100, 200])
                problem_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('TOPPADDING', (0, 1), (-1, -1), 3),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 3),
                ]))
                elements.append(problem_table)
            else:
                elements.append(Paragraph("No problematic data types found in the schema.", styles['Normal']))
            
            elements.append(Spacer(1, 12))
            
            # 2. Relationship Analysis
            elements.append(Paragraph("Relationship Analysis", styles['Heading3']))
            
            # High connectivity tables
            high_conn = self.analysis_results['relationships']['high_connectivity_tables']
            if high_conn:
                elements.append(Paragraph("Tables with High Connectivity (potential query complexity):", styles['Normal']))
                
                conn_data = [["Table", "Incoming Refs", "Outgoing Refs", "Total"]]
                for table in high_conn:
                    conn_data.append([
                        table['table'],
                        str(table['in_references']),
                        str(table['out_references']),
                        str(table['total_connections'])
                    ])
                
                conn_table = Table(conn_data, colWidths=[150, 100, 100, 100])
                conn_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
                    ('TOPPADDING', (0, 1), (-1, -1), 3),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 3),
                ]))
                elements.append(conn_table)
                elements.append(Spacer(1, 8))
                
                # Add note about high connectivity
                elements.append(Paragraph("Note: Tables with high connectivity often represent good candidates for denormalization in Cassandra.", 
                                         ParagraphStyle('Note', fontName='Helvetica-Oblique', fontSize=10, textColor=colors.gray)))
            else:
                elements.append(Paragraph("No tables with high connectivity found in the schema.", styles['Normal']))
            
            elements.append(Spacer(1, 12))
            
            # 3. Access Pattern Analysis
            elements.append(Paragraph("Access Pattern Analysis", styles['Heading3']))
            
            if 'access_patterns' in self.analysis_results and not self.analysis_results['access_patterns'].get('no_queries_provided', False):
                # Most queried tables
                most_queried = self.analysis_results['access_patterns']['most_queried_tables']
                elements.append(Paragraph("Most Frequently Queried Tables:", styles['Normal']))
                
                query_data = [["Table", "Query Count"]]
                for table, count in most_queried:
                    query_data.append([table, str(count)])
                
                query_table = Table(query_data, colWidths=[200, 100])
                query_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('ALIGN', (1, 1), (1, -1), 'CENTER'),
                    ('TOPPADDING', (0, 1), (-1, -1), 3),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 3),
                ]))
                elements.append(query_table)
                
                elements.append(Spacer(1, 8))
                
                # Most common WHERE conditions
                most_where = self.analysis_results['access_patterns']['most_common_where']
                elements.append(Paragraph("Most Common WHERE Conditions:", styles['Normal']))
                
                where_data = [["Column", "Frequency"]]
                for col, count in most_where:
                    where_data.append([col, str(count)])
                
                where_table = Table(where_data, colWidths=[200, 100])
                where_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('ALIGN', (1, 1), (1, -1), 'CENTER'),
                    ('TOPPADDING', (0, 1), (-1, -1), 3),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 3),
                ]))
                elements.append(where_table)
                
                # Add note about WHERE conditions
                elements.append(Paragraph("Note: Columns frequently used in WHERE clauses should be considered for partition keys in Cassandra.", 
                                         ParagraphStyle('Note', fontName='Helvetica-Oblique', fontSize=10, textColor=colors.gray)))
            else:
                elements.append(Paragraph("No query patterns provided for analysis.", styles['Normal']))
            
            # Page break before best practices
            elements.append(PageBreak())
            
            # Best Practices Scorecard
            elements.append(Paragraph("Cassandra Best Practices Scorecard", styles['Heading2']))
            
            # 1. Primary Keys
            elements.append(Paragraph("Primary Key Design", styles['Heading3']))
            pk_score = self.best_practices_score['categories']['primary_keys']['score']
            elements.append(Paragraph(f"Score: {pk_score:.1f}/100", styles['Normal']))
            
            # Primary key table
            pk_data = [["Table", "Primary Key Structure", "Score", "Issues"]]
            for detail in self.best_practices_score['categories']['primary_keys']['details']:
                pk_data.append([
                    detail['table'],
                    ", ".join(self.analysis_results['table_structure']['table_stats'][detail['table']]['primary_key']),
                    f"{detail['score']:.0f}/100",
                    "; ".join(detail['issues'])
                ])
            
            pk_table = Table(pk_data, colWidths=[100, 150, 50, 200])
            pk_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('ALIGN', (2, 1), (2, -1), 'CENTER'),
                ('TOPPADDING', (0, 1), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 3),
            ]))
            elements.append(pk_table)
            
            elements.append(Spacer(1, 8))
            
            elements.append(Paragraph("Cassandra Primary Key Best Practices:", styles['Normal']))
            pk_items = [
                ListItem(Paragraph("Partition keys should distribute data evenly across nodes", styles['Normal'])),
                ListItem(Paragraph("Avoid high-cardinality partition keys to prevent hotspots", styles['Normal'])),
                ListItem(Paragraph("Use composite keys (partition key + clustering columns) for efficient data retrieval", styles['Normal'])),
                ListItem(Paragraph("Order clustering columns based on query patterns", styles['Normal'])),
                ListItem(Paragraph("Keep related data in the same partition to minimize reads", styles['Normal']))
            ]
            elements.append(ListFlowable(pk_items, bulletType='bullet', leftIndent=20))
            
            elements.append(Spacer(1, 12))
            
            # 2. Data Types
            elements.append(Paragraph("Data Type Selection", styles['Heading3']))
            dt_score = self.best_practices_score['categories']['data_types']['score']
            elements.append(Paragraph(f"Score: {dt_score:.1f}/100", styles['Normal']))
            
            elements.append(Paragraph("Cassandra Data Type Best Practices:", styles['Normal']))
            dt_items = [
                ListItem(Paragraph("Use text instead of varchar for string data", styles['Normal'])),
                ListItem(Paragraph("Prefer bigint over decimal for numeric values requiring precision", styles['Normal'])),
                ListItem(Paragraph("Use collections (list, set, map) for small groups of related data", styles['Normal'])),
                ListItem(Paragraph("Use UUID type for globally unique identifiers", styles['Normal'])),
                ListItem(Paragraph("Avoid using floating-point types for exact calculations", styles['Normal']))
            ]
            elements.append(ListFlowable(dt_items, bulletType='bullet', leftIndent=20))
            
            elements.append(Spacer(1, 12))
            
            # 3. Denormalization Strategies
            elements.append(Paragraph("Denormalization Strategies", styles['Heading3']))
            denorm_score = self.best_practices_score['categories']['denormalization']['score']
            elements.append(Paragraph(f"Score: {denorm_score:.1f}/100", styles['Normal']))
            
            elements.append(Paragraph("Cassandra Denormalization Best Practices:", styles['Normal']))
            denorm_items = [
                ListItem(Paragraph("Design tables around query patterns, not entity relationships", styles['Normal'])),
                ListItem(Paragraph("Duplicate data across tables to minimize joins", styles['Normal'])),
                ListItem(Paragraph("Use collections for one-to-few relationships", styles['Normal'])),
                ListItem(Paragraph("Create separate tables for each query pattern", styles['Normal'])),
                ListItem(Paragraph("Accept data duplication to optimize read performance", styles['Normal']))
            ]
            elements.append(ListFlowable(denorm_items, bulletType='bullet', leftIndent=20))
            
            # Add top denormalization recommendations
            denorm_recs = [r for r in self.recommendations if r['category'] == 'Denormalization']
            if denorm_recs:
                elements.append(Paragraph("Top Denormalization Recommendations:", styles['Normal']))
                
                rec_items = []
                for i, rec in enumerate(denorm_recs[:3]):  # Limit to top 3
                    rec_text = f"<b>{rec['table']}:</b> {rec['recommendation']}<br/>{rec['suggested_fix']}"
                    rec_items.append(ListItem(Paragraph(rec_text, styles['Normal'])))
                
                elements.append(ListFlowable(rec_items, bulletType='bullet', leftIndent=20))
            
            elements.append(Spacer(1, 12))
            
            # 4. Query Patterns
            elements.append(Paragraph("Query Pattern Alignment", styles['Heading3']))
            query_score = self.best_practices_score['categories']['query_patterns']['score']
            elements.append(Paragraph(f"Score: {query_score:.1f}/100", styles['Normal']))
            
            elements.append(Paragraph("Cassandra Query Pattern Best Practices:", styles['Normal']))
            query_items = [
                ListItem(Paragraph("Design tables based on specific query requirements", styles['Normal'])),
                ListItem(Paragraph("Include all filtering columns in primary key", styles['Normal'])),
                ListItem(Paragraph("Order clustering columns based on sorting needs", styles['Normal'])),
                ListItem(Paragraph("Create separate tables for different access patterns", styles['Normal'])),
                ListItem(Paragraph("Avoid secondary indexes except for low-cardinality columns", styles['Normal']))
            ]
            elements.append(ListFlowable(query_items, bulletType='bullet', leftIndent=20))
            
            # Build the document
            doc.build(elements)
            
            print(f"PDF report generated successfully: {output_file}")
            return True
        except Exception as e:
            print(f"Error generating PDF report: {e}")
            return False
            
    def _create_score_chart(self):
        """Create a chart showing scores by category."""
        drawing = Drawing(400, 200)
        
        data = [
            [self.best_practices_score['categories']['primary_keys']['score'],
             self.best_practices_score['categories']['data_types']['score'],
             self.best_practices_score['categories']['denormalization']['score'],
             self.best_practices_score['categories']['query_patterns']['score']]
        ]
        
        # Create and customize the bar chart
        chart = VerticalBarChart()
        chart.x = 50
        chart.y = 50
        chart.height = 125
        chart.width = 300
        chart.data = data
        chart.valueAxis.valueMin = 0
        chart.valueAxis.valueMax = 100
        chart.valueAxis.valueStep = 20
        chart.categoryAxis.labels.boxAnchor = 'ne'
        chart.categoryAxis.labels.dx = -8
        chart.categoryAxis.labels.dy = -2
        chart.categoryAxis.labels.angle = 30
        chart.categoryAxis.labels.fontName = 'Helvetica'
        chart.categoryAxis.categoryNames = ['Primary Keys', 'Data Types', 'Denormalization', 'Query Patterns']
        
        # Set bar colors
        chart.bars[0].fillColor = colors.steelblue
        
        drawing.add(chart)
        return drawing

def main():
    parser = argparse.ArgumentParser(description='Analyze relational schema and generate Cassandra best practices report')
    parser.add_argument('--schema', '-s', required=True, help='Input schema JSON file')
    parser.add_argument('--queries', '-q', help='File containing common query patterns (optional)')
    parser.add_argument('--output', '-o', required=True, help='Output PDF report file')
    
    args = parser.parse_args()
    
    analyzer = SchemaAnalyzer()
    
    # Load schema
    if not analyzer.load_schema(args.schema):
        return 1
    
    # Load queries if provided
    if args.queries:
        analyzer.load_queries(args.queries)
    
    # Analyze schema
    if not analyzer.analyze_schema():
        return 1
    
    # Generate PDF report
    if not analyzer.generate_pdf_report(args.output):
        return 1
    
    print(f"\nAnalysis complete!")
    print(f"- PDF report saved to: {args.output}")
    
    return 0

if __name__ == "__main__":
    exit(main())
