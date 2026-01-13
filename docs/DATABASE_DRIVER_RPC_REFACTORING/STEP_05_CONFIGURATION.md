# Step 5: Configuration Structure

**Priority**: Foundation  
**Dependencies**: None  
**Estimated Time**: 1 week

## Goal

Add database driver configuration to config schema.

## Implementation Status

**Status**: ❌ **NOT IMPLEMENTED** (0%)

### Current State:
- ✅ **Config system exists**: `code_analysis/core/config.py` and `config_validator.py`
- ❌ **Driver config section**: Not found in config schema
- ❌ **Driver config validation**: Not implemented
- ❌ **Driver config loading**: Not implemented in main.py

### Missing Components:
- Driver config model in `config.py`
- Driver validation in `config_validator.py`
- Driver config section in `config.json`
- Driver config loading in `main.py`

**See**: [Implementation Status Analysis](./IMPLEMENTATION_STATUS_ANALYSIS.md) for detailed comparison.

## Code Mapper Requirements

**⚠️ CRITICAL: Must use code_mapper utility throughout implementation**

### Before Writing Code
- [ ] **ALWAYS run code_mapper** to check if functionality already exists in project
- [ ] Search existing config code using `code_mapper` indexes
- [ ] Review existing `code_analysis/core/config.py` and `config_validator.py`
- [ ] Check for existing configuration patterns
- [ ] Use command: `code_mapper -r code_analysis/` (excludes tests and test_data)

### During Code Implementation
- [ ] **Run code_mapper after each block of changes** to update indexes
- [ ] Use command: `code_mapper -r code_analysis/` to update indexes

### After Writing Code (Production Code Only, Not Tests)
- [ ] **⚠️ CRITICAL: Run code_mapper** to check for errors and issues
- [ ] **Command**: `code_mapper -r code_analysis/` (excludes tests and test_data from analysis)
- [ ] **Eliminate ALL errors** found by code_mapper utility - this is MANDATORY
- [ ] Fix all code quality issues detected by code_mapper
- [ ] **DO NOT proceed until ALL code_mapper errors are fixed**

**⚠️ IMPORTANT**: 
- Always use `code_mapper -r code_analysis/` to exclude tests and test_data
- After writing production code, you MUST run code_mapper and fix ALL errors
- Test files are excluded from code_mapper analysis
- All production code errors must be eliminated before proceeding

## Checklist

- [ ] Update `config.json` schema to include `code_analysis.database.driver` section
- [ ] Update `CodeAnalysisConfigValidator` to validate driver config
- [ ] Add driver config loading in `main.py`
- [ ] Create helper function `get_driver_config()` to extract driver config from full config
- [ ] Test config validation with valid/invalid driver configs
- [ ] Test config loading from `config.json`

## Files to Modify

- `code_analysis/core/config_validator.py` - Add validation for driver config
- `code_analysis/core/config.py` - Add driver config model (optional)
- `config.json` - Add example driver config

## Testing Requirements

**⚠️ CRITICAL: Test Coverage Must Be 90%+**

### Unit Tests
- [ ] Config validation with valid/invalid driver configs
- [ ] Config loading from config.json
- [ ] Helper function `get_driver_config()`
- [ ] **Coverage: 90%+ for config validation**

### Integration Tests with Real Data
- [ ] **Test config loading with real config.json**
- [ ] Test config validation with real project configs
- [ ] Test driver config extraction from real configs

## Deliverables

- ✅ Config schema supports `code_analysis.database.driver.type` and `code_analysis.database.driver.config`
- ✅ Config validator validates driver configuration
- ✅ Helper function to extract driver config
- ✅ **Test coverage 90%+**

## Next Steps

- [Step 2: RPC Infrastructure](./STEP_02_RPC_INFRASTRUCTURE.md)
