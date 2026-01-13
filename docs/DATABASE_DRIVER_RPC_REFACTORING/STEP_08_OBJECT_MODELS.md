# Step 8: Object Models

**Priority**: API Development  
**Dependencies**: Step 4 (Client Implementation)  
**Estimated Time**: 2 weeks

## Goal

Create object-oriented models for database entities.

## Code Mapper Requirements

**⚠️ CRITICAL: Must use code_mapper utility throughout implementation**

### Before Writing Code
- [ ] **ALWAYS run code_mapper** to check if functionality already exists in project
- [ ] Search existing object models using `code_mapper` indexes
- [ ] Review existing database entity classes if any
- [ ] Check for existing serialization patterns
- [ ] Use command: `code_mapper -r code_analysis/` (excludes tests and test_data)

### During Code Implementation
- [ ] **Run code_mapper after each block of changes** to update indexes
- [ ] Use command: `code_mapper -r code_analysis/` to update indexes

### After Writing Code (Production Code Only, Not Tests)
- [ ] **⚠️ CRITICAL: Run code_mapper** to check for errors and issues
- [ ] **Command**: `code_mapper -r code_analysis/` (excludes tests and test_data from analysis)
- [ ] **Eliminate ALL errors** found by code_mapper utility - this is MANDATORY
- [ ] Fix all code quality issues detected by code_mapper
- [ ] Verify no duplicate code was introduced
- [ ] Check file sizes (must be < 400 lines)
- [ ] **DO NOT proceed until ALL code_mapper errors are fixed**

**⚠️ IMPORTANT**: 
- Always use `code_mapper -r code_analysis/` to exclude tests and test_data
- After writing production code, you MUST run code_mapper and fix ALL errors
- Test files are excluded from code_mapper analysis
- All production code errors must be eliminated before proceeding

## Checklist

### 8.1 Core Objects
- [ ] Create `Project` class
- [ ] Create `Dataset` class
- [ ] Create `File` class
- [ ] Implement serialization/deserialization

### 8.2 Attribute Objects
- [ ] Create `ASTNode` class
- [ ] Create `CSTNode` class
- [ ] Create `VectorIndex` class
- [ ] Create `CodeChunk` class

### 8.3 Code Structure Objects
- [ ] Create `Class` class
- [ ] Create `Function` class
- [ ] Create `Method` class
- [ ] Create `Import` class

### 8.4 Analysis Objects
- [ ] Create `Issue` class
- [ ] Create `Usage` class
- [ ] Create `CodeDuplicate` class

### 8.5 Object-to-Database Mapping
- [ ] Create mapper functions to convert objects to database rows
- [ ] Create mapper functions to convert database rows to objects
- [ ] Handle relationships between objects

## Files to Create

- `code_analysis/core/database_client/objects/__init__.py`
- `code_analysis/core/database_client/objects/project.py`
- `code_analysis/core/database_client/objects/dataset.py`
- `code_analysis/core/database_client/objects/file.py`
- `code_analysis/core/database_client/objects/attributes.py`
- `code_analysis/core/database_client/objects/code_structure.py`
- `code_analysis/core/database_client/objects/analysis.py`
- `code_analysis/core/database_client/objects/mappers.py`

## Testing Requirements

**⚠️ CRITICAL: Test Coverage Must Be 90%+**

### Unit Tests
- [ ] All object models (Project, File, Dataset, etc.)
- [ ] Serialization/deserialization
- [ ] Object-to-database mapping
- [ ] Database-to-object mapping
- [ ] Object relationships
- [ ] **Coverage: 90%+ for all object models**

### Integration Tests with Real Data
- [ ] **Test object models with real data from test_data/**
- [ ] Test Project object with real projects (vast_srv, bhlff)
- [ ] Test File object with real files from test_data
- [ ] Test object-to-database mapping with real data
- [ ] Test database-to-object mapping with real data
- [ ] Verify all object models work correctly with real data

## Deliverables

- ✅ All object models created
- ✅ Serialization/deserialization works
- ✅ Object-to-database mapping works
- ✅ **Test coverage 90%+**
- ✅ **All tests pass on real data from test_data/**

## Next Steps

- [Step 9: High-Level Client API](./STEP_09_CLIENT_API.md)
