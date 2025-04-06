#!/usr/bin/env python3
"""
Relational to Cassandra Schema Converter

This script analyzes a relational database schema and converts it to an optimized
Cassandra data model, focusing on:
1. Denormalizing data based on access patterns
2. Creating appropriate partition keys and clustering columns
3. Handling relationships through data duplication
4. Optimizing for Cassandra's distributed architecture

Usage:
    python3 rel_to_cassandra.py --input schema.json --output cassandra_schema.cql --queries queries.txt
"""

import json
import argparse
import re
import os
from collections import defaultdict

class RelationalToCassandraConverter:
    def __init__(self):
        self.relational_tables = {}
        self.foreign_keys = defaultdict(list)
        self.relationships = defaultdict(list)
        self.access_patterns = []
        self.cassandra_tables = {}
        
    def load_schema(self, schema_file):
        """Load relational schema from JSON file."""
        try:
            with open(schema_file, 'r') as f:
                schema_data = json.load(f)
                
            # Extract tables, columns, primary keys, and foreign keys
            for table_info in schema_data.get('tables', []):
                table_name = table_info['name']
                self.relational_tables[table_name] = {
                    'columns': {},
                    'primary_key': []
                }
                
                # Process columns
                for column in table_info.get('columns', []):
                    col_name = column['name']
                    self.relational_tables[table_name]['columns'][col_name] = {
                        'type': self._map_data_type(column['type']),
                        'nullable': column.get('nullable', True)
                    }
                    
                    if column.get('primary_key', False):
                        self.relational_tables[table_name]['primary_key'].append(col_name)
                
                # Process foreign keys
                for fk in table_info.get('foreign_keys', []):
                    reference = fk.get('references', {})
                    self.foreign_keys[table_name].append({
                        'column': fk['column'],
                        'references_table': reference.get('table'),
                        'references_column': reference.get('column')
                    })
                    
                    # Track relationships for denormalization
                    ref_table = reference.get('table')
                    if ref_table:
                        self.relationships[table_name].append(ref_table)
                        self.relationships[ref_table].append(table_name)
            
            print(f"Loaded schema with {len(self.relational_tables)} tables")
            return True
        except Exception as e:
            print(f"Error loading schema: {e}")
            return False
            
    def load_queries(self, queries_file):
        """
        Load common query patterns to help design the Cassandra model.
        Each query should be on a separate line.
        """
        if not os.path.exists(queries_file):
            print(f"Queries file {queries_file} not found. Continuing without query analysis.")
            return
            
        try:
            with open(queries_file, 'r') as f:
                query_lines = f.readlines()
                
            for line in query_lines:
                query = line.strip()
                if query and not query.startswith('#'):
                    # Extract tables and conditions from the query
                    tables = self._extract_tables_from_query(query)
                    conditions = self._extract_conditions_from_query(query)
                    ordering = self._extract_ordering_from_query(query)
                    
                    self.access_patterns.append({
                        'tables': tables,
                        'conditions': conditions,
                        'ordering': ordering
                    })
            
            print(f"Loaded {len(self.access_patterns)} query patterns for analysis")
        except Exception as e:
            print(f"Error loading queries: {e}")
    
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
    
    def _map_data_type(self, relational_type):
        """Map relational data types to Cassandra data types."""
        relational_type = relational_type.lower()
        
        # Mapping of common SQL types to Cassandra types
        type_map = {
            'int': 'int',
            'integer': 'int',
            'smallint': 'smallint',
            'bigint': 'bigint',
            'tinyint': 'tinyint',
            'varchar': 'text',
            'char': 'text',
            'text': 'text',
            'string': 'text',
            'float': 'float',
            'double': 'double',
            'decimal': 'decimal',
            'boolean': 'boolean',
            'bool': 'boolean',
            'date': 'date',
            'time': 'time',
            'timestamp': 'timestamp',
            'datetime': 'timestamp',
            'uuid': 'uuid',
            'blob': 'blob'
        }
        
        # Handle types with length specifications like varchar(255)
        base_type = relational_type.split('(')[0].lower()
        
        if base_type in type_map:
            return type_map[base_type]
        else:
            print(f"Warning: Unknown data type '{relational_type}', defaulting to 'text'")
            return 'text'
    
    def analyze_and_convert(self):
        """Analyze the relational schema and convert to Cassandra tables."""
        if not self.relational_tables:
            print("No relational schema loaded. Please load a schema first.")
            return False
        
        # Analyze tables and determine access patterns
        self._analyze_relationships()
        
        # Create Cassandra tables based on analysis
        self._create_cassandra_tables()
        
        return True
    
    def _analyze_relationships(self):
        """Analyze relationships between tables to guide denormalization."""
        print("Analyzing table relationships...")
        
        # For each table, determine potential denormalizations based on relationships
        for table_name, related_tables in self.relationships.items():
            print(f"Table '{table_name}' has relationships with: {', '.join(related_tables)}")
            
        # Identify tables frequently queried together (from access patterns)
        table_pairs = []
        for pattern in self.access_patterns:
            tables = pattern['tables']
            for i in range(len(tables)):
                for j in range(i+1, len(tables)):
                    table_pairs.append((tables[i], tables[j]))
        
        # Count frequency of table pairs
        pair_counts = defaultdict(int)
        for pair in table_pairs:
            pair_counts[pair] += 1
            
        # Print most common table pairings
        if pair_counts:
            print("\nMost common table pairings in queries:")
            for pair, count in sorted(pair_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"  {pair[0]} and {pair[1]}: {count} occurrences")
    
    def _create_cassandra_tables(self):
        """Create Cassandra tables based on analysis."""
        print("\nCreating Cassandra tables...")
        
        # First pass: Create base tables from relational tables
        for table_name, table_info in self.relational_tables.items():
            # Start with direct table conversion
            cassandra_table_name = table_name.lower()
            
            # Determine partition key and clustering columns
            partition_key = []
            clustering_columns = []
            
            # Use primary key from relational model as starting point
            primary_key = table_info['primary_key']
            
            if primary_key:
                # First column of PK becomes partition key by default
                partition_key = [primary_key[0]]
                # Rest become clustering columns
                clustering_columns = primary_key[1:] if len(primary_key) > 1 else []
            else:
                # If no PK, we'll need to create one (possibly using a UUID)
                partition_key = ['id']
                print(f"Warning: Table '{table_name}' has no primary key. Using 'id' as default partition key.")
            
            # Adjust based on access patterns
            self._adjust_keys_from_access_patterns(table_name, partition_key, clustering_columns)
            
            # Define columns
            columns = {}
            for col_name, col_info in table_info['columns'].items():
                columns[col_name.lower()] = col_info['type']
                
            # If we added an 'id' partition key but it doesn't exist, add it
            if 'id' in partition_key and 'id' not in columns:
                columns['id'] = 'uuid'
                
            # Store the Cassandra table definition
            self.cassandra_tables[cassandra_table_name] = {
                'columns': columns,
                'partition_key': partition_key,
                'clustering_columns': clustering_columns
            }
        
        # Second pass: Create denormalized tables based on relationships and access patterns
        self._create_denormalized_tables()
    
    def _adjust_keys_from_access_patterns(self, table_name, partition_key, clustering_columns):
        """Adjust partition keys and clustering columns based on query patterns."""
        table_patterns = [p for p in self.access_patterns if table_name in p['tables']]
        
        if not table_patterns:
            return
            
        # Look for columns frequently used in WHERE clauses
        where_columns = []
        for pattern in table_patterns:
            where_columns.extend(pattern['conditions'])
            
        # Count frequency of each column in WHERE clauses
        col_counts = defaultdict(int)
        for col in where_columns:
            col_counts[col] += 1
            
        # Find the most common WHERE column
        if col_counts:
            most_common = max(col_counts.items(), key=lambda x: x[1])[0]
            if most_common in self.relational_tables[table_name]['columns']:
                # If it's not already in primary key, consider it for partition key
                if most_common not in partition_key + clustering_columns:
                    # Replace partition key or add it
                    if not partition_key:
                        partition_key.append(most_common)
                    else:
                        print(f"Consider using '{most_common}' as partition key for table '{table_name}'")
        
        # Look for columns used in ORDER BY
        order_columns = []
        for pattern in table_patterns:
            order_columns.extend(pattern['ordering'])
            
        # Add order columns to clustering columns if not already there
        for col in order_columns:
            if col in self.relational_tables[table_name]['columns'] and col not in partition_key and col not in clustering_columns:
                clustering_columns.append(col)
                print(f"Added '{col}' as clustering column for table '{table_name}'")
    
    def _create_denormalized_tables(self):
        """Create denormalized tables based on relationships and access patterns."""
        print("\nCreating denormalized tables based on relationships...")
        
        # Identify candidate tables for denormalization from access patterns
        denorm_candidates = []
        
        for pattern in self.access_patterns:
            tables = pattern['tables']
            if len(tables) >= 2:
                # If multiple tables are queried together, they're candidates for denormalization
                for i in range(len(tables)):
                    for j in range(i+1, len(tables)):
                        t1, t2 = tables[i], tables[j]
                        # Check if there's a relationship between these tables
                        if t2 in self.relationships.get(t1, []) or t1 in self.relationships.get(t2, []):
                            denorm_candidates.append((t1, t2))
        
        # Create denormalized tables for frequent patterns
        created_denorm_tables = set()
        for t1, t2 in denorm_candidates:
            denorm_name = f"{t1.lower()}_{t2.lower()}_by"
            
            # Skip if we already created this denormalized table
            if denorm_name in created_denorm_tables:
                continue
                
            # Determine the direction of the relationship
            is_t1_parent = any(fk['references_table'] == t1 for fk in self.foreign_keys.get(t2, []))
            is_t2_parent = any(fk['references_table'] == t2 for fk in self.foreign_keys.get(t1, []))
            
            if is_t1_parent:
                # t1 is parent, t2 is child
                self._create_parent_child_denormalized_table(t1, t2)
                created_denorm_tables.add(denorm_name)
            elif is_t2_parent:
                # t2 is parent, t1 is child
                self._create_parent_child_denormalized_table(t2, t1)
                created_denorm_tables.add(denorm_name)
            else:
                # Many-to-many or no direct relationship
                print(f"No direct parent-child relationship found between {t1} and {t2}")
    
    def _create_parent_child_denormalized_table(self, parent, child):
        """Create a denormalized table combining a parent and child table."""
        parent_info = self.relational_tables.get(parent)
        child_info = self.relational_tables.get(child)
        
        if not parent_info or not child_info:
            return
            
        # Get foreign key column linking child to parent
        fk_column = None
        for fk in self.foreign_keys.get(child, []):
            if fk['references_table'] == parent:
                fk_column = fk['column']
                break
                
        if not fk_column:
            print(f"Couldn't find foreign key from {child} to {parent}")
            return
            
        # Create table name
        denorm_name = f"{parent.lower()}_with_{child.lower()}"
        
        # Start with parent's columns and keys
        columns = parent_info['columns'].copy()
        partition_key = parent_info['primary_key'][:1] if parent_info['primary_key'] else ['id']
        clustering_columns = []
        
        # Add relevant columns from child (except the FK column)
        for col_name, col_info in child_info['columns'].items():
            if col_name != fk_column:
                # Add a prefix to avoid name collisions
                new_col_name = f"{child.lower()}_{col_name.lower()}"
                columns[new_col_name] = col_info
        
        # Add child's primary key (except FK) to clustering columns
        for pk_col in child_info['primary_key']:
            if pk_col != fk_column:
                clustering_col = f"{child.lower()}_{pk_col.lower()}"
                clustering_columns.append(clustering_col)
        
        # Store the denormalized table
        self.cassandra_tables[denorm_name] = {
            'columns': {col_name.lower(): col_type for col_name, col_type in columns.items()},
            'partition_key': partition_key,
            'clustering_columns': clustering_columns,
            'denormalized': True,
            'source_tables': [parent, child]
        }
        
        print(f"Created denormalized table '{denorm_name}' combining {parent} and {child}")
        
        # Also create a table for querying child records by parent
        by_parent_name = f"{child.lower()}_by_{parent.lower()}"
        
        # Convert columns to dict with types
        by_parent_columns = {}
        for col_name, col_info in child_info['columns'].items():
            by_parent_columns[col_name.lower()] = col_info['type']
            
        # Add parent's primary key as the partition key
        partition_col = parent_info['primary_key'][0].lower()
        by_parent_columns[partition_col] = parent_info['columns'][parent_info['primary_key'][0]]['type']
        
        self.cassandra_tables[by_parent_name] = {
            'columns': by_parent_columns,
            'partition_key': [partition_col],
            'clustering_columns': [col.lower() for col in child_info['primary_key'] if col != fk_column],
            'denormalized': True,
            'source_tables': [parent, child],
            'query_pattern': f"SELECT * FROM {by_parent_name} WHERE {partition_col} = ?"
        }
        
        print(f"Created lookup table '{by_parent_name}' for querying {child} by {parent}")
    
    def generate_cql(self):
        """Generate CQL statements for the Cassandra schema."""
        if not self.cassandra_tables:
            print("No Cassandra tables defined. Please analyze and convert first.")
            return ""
            
        cql_statements = [
            "-- Cassandra Schema Generated from Relational Model",
            "-- Generated by Relational to Cassandra Converter\n",
            "-- Create keyspace (adjust replication strategy as needed)",
            "CREATE KEYSPACE IF NOT EXISTS converted_schema WITH REPLICATION = {",
            "    'class': 'SimpleStrategy',",
            "    'replication_factor': 3",
            "};\n",
            "USE converted_schema;\n"
        ]
        
        # Generate CQL for each table
        for table_name, table_info in self.cassandra_tables.items():
            # Add comment for denormalized tables
            if table_info.get('denormalized'):
                source_tables = table_info.get('source_tables', [])
                cql_statements.append(f"-- Denormalized table combining {' and '.join(source_tables)}")
                if 'query_pattern' in table_info:
                    cql_statements.append(f"-- Query pattern: {table_info['query_pattern']}")
            
            # Start CREATE TABLE statement
            cql_statements.append(f"CREATE TABLE IF NOT EXISTS {table_name} (")
            
            # Add columns
            column_lines = []
            for col_name, col_type in table_info['columns'].items():
                column_lines.append(f"    {col_name} {col_type}")
            
            # Add primary key
            pk_parts = []
            if table_info['partition_key']:
                if len(table_info['partition_key']) == 1:
                    pk_parts.append(table_info['partition_key'][0].lower())
                else:
                    pk_parts.append(f"({', '.join(col.lower() for col in table_info['partition_key'])})")
                    
            if table_info['clustering_columns']:
                pk_parts.extend(col.lower() for col in table_info['clustering_columns'])
                
            if pk_parts:
                column_lines.append(f"    PRIMARY KEY ({', '.join(pk_parts)})")
            
            cql_statements.append(',\n'.join(column_lines))
            
            # Add WITH clause for clustering order if needed
            if table_info['clustering_columns']:
                cql_statements.append(") WITH CLUSTERING ORDER BY (")
                order_parts = [f"{col.lower()} ASC" for col in table_info['clustering_columns']]
                cql_statements.append(', '.join(order_parts))
                cql_statements.append(");")
            else:
                cql_statements.append(");")
            
            # Add empty line between tables
            cql_statements.append("")
        
        # Add notes on usage
        cql_statements.append("-- Notes on Cassandra Data Model:")
        cql_statements.append("-- 1. Tables are designed to optimize for specific query patterns")
        cql_statements.append("-- 2. Data is denormalized - the same data may exist in multiple tables")
        cql_statements.append("-- 3. Updates must be performed on all tables containing the data")
        cql_statements.append("-- 4. Always query by partition key for best performance")
        
        return '\n'.join(cql_statements)
    
    def save_cql(self, output_file):
        """Save the generated CQL to a file."""
        cql = self.generate_cql()
        
        if cql:
            try:
                with open(output_file, 'w') as f:
                    f.write(cql)
                print(f"CQL schema saved to {output_file}")
                return True
            except Exception as e:
                print(f"Error saving CQL: {e}")
                return False
        return False
    
    def generate_access_pattern_summary(self):
        """Generate a summary of access patterns and recommended query practices."""
        if not self.cassandra_tables:
            return "No Cassandra tables defined. Please analyze and convert first."
            
        lines = [
            "# Cassandra Access Pattern Summary",
            "",
            "## Generated Tables",
            ""
        ]
        
        # List all tables with purpose
        for table_name, table_info in self.cassandra_tables.items():
            lines.append(f"### {table_name}")
            
            # Show if it's denormalized and source tables
            if table_info.get('denormalized'):
                source_tables = table_info.get('source_tables', [])
                lines.append(f"- Denormalized from: {', '.join(source_tables)}")
            
            # Show partition key and clustering columns
            pk_str = ', '.join(table_info['partition_key'])
            lines.append(f"- Partition key: {pk_str}")
            
            if table_info['clustering_columns']:
                cc_str = ', '.join(table_info['clustering_columns'])
                lines.append(f"- Clustering columns: {cc_str}")
            
            # Show recommended query pattern if available
            if 'query_pattern' in table_info:
                lines.append(f"- Query pattern: `{table_info['query_pattern']}`")
                
            lines.append("")
        
        lines.extend([
            "## Best Practices for Cassandra Queries",
            "",
            "1. **Always query by partition key** to avoid full cluster scans",
            "2. **Use prepared statements** for better performance",
            "3. **Be mindful of data consistency** when updating denormalized data",
            "4. **Consider time-to-live (TTL)** for data that should expire",
            "5. **Monitor partition sizes** to avoid hotspots",
            "",
            "## Data Modeling Decisions",
            ""
        ])
        
        # Explain key data modeling decisions
        for table_name, table_info in self.cassandra_tables.items():
            if table_info.get('denormalized'):
                source_tables = table_info.get('source_tables', [])
                lines.append(f"- **{table_name}**: Denormalized to optimize queries across {' and '.join(source_tables)}")
        
        return '\n'.join(lines)
    
    def save_access_pattern_summary(self, output_file):
        """Save the access pattern summary to a file."""
        summary = self.generate_access_pattern_summary()
        
        if summary:
            try:
                with open(output_file, 'w') as f:
                    f.write(summary)
                print(f"Access pattern summary saved to {output_file}")
                return True
            except Exception as e:
                print(f"Error saving access pattern summary: {e}")
                return False
        return False

def main():
    parser = argparse.ArgumentParser(description='Convert relational schema to Cassandra schema')
    parser.add_argument('--input', '-i', required=True, help='Input schema JSON file')
    parser.add_argument('--output', '-o', required=True, help='Output CQL file')
    parser.add_argument('--queries', '-q', help='File containing common query patterns (optional)')
    parser.add_argument('--summary', '-s', help='Output file for access pattern summary (optional)')
    
    args = parser.parse_args()
    
    converter = RelationalToCassandraConverter()
    
    # Load schema
    if not converter.load_schema(args.input):
        return 1
    
    # Load queries if provided
    if args.queries:
        converter.load_queries(args.queries)
    
    # Analyze and convert
    if not converter.analyze_and_convert():
        return 1
    
    # Save CQL
    if not converter.save_cql(args.output):
        return 1
    
    # Save summary if requested
    if args.summary:
        converter.save_access_pattern_summary(args.summary)
    
    print("\nConversion complete!")
    print(f"- CQL schema saved to: {args.output}")
    if args.summary:
        print(f"- Access pattern summary saved to: {args.summary}")
    
    return 0

if __name__ == "__main__":
    exit(main())
