import pytest
import os
import sqlite3
from atlas_ui.backend.database.sqlite_store import SQLiteStore
from atlas_ui.backend.identity.account_registry import AccountRegistry
from atlas_ui.backend.identity.person_registry import PersonRegistry

@pytest.fixture
def temp_db_path(tmpdir):
    return str(tmpdir.join("test_persistence.db"))

def test_restart_persistence(temp_db_path):
    # 1. Start application (create DB and write)
    store1 = SQLiteStore(temp_db_path)
    acc_reg1 = AccountRegistry(store1)
    person_reg1 = PersonRegistry(store1)
    
    acc1 = acc_reg1.create_account("p_user", "hash", "salt", "USER")
    person1 = person_reg1.create_person("P User", account_id=acc1.account_id, role="USER")
    
    assert acc1.username == "p_user"
    assert person1.display_name == "P User"
    
    # 2. Restart application (new registry instances, same DB)
    store2 = SQLiteStore(temp_db_path)
    
    # Simulate loading from SQLite on startup
    acc_reg2 = AccountRegistry(store2)
    for row in store2.get_all_accounts():
        acc_reg2._accounts[row["account_id"]] = type('obj', (object,), {
            "account_id": row["account_id"],
            "username": row["username"]
        })()
        
    person_reg2 = PersonRegistry(store2)
    for row in store2.get_all_persons():
        person_reg2._people[row["person_id"]] = type('obj', (object,), {
            "atlas_person_id": row["person_id"],
            "display_name": row["display_name"]
        })()
        
    assert len(acc_reg2._accounts) == 1
    assert len(person_reg2._people) == 1
    
    recovered_acc = list(acc_reg2._accounts.values())[0]
    recovered_person = list(person_reg2._people.values())[0]
    
    assert recovered_acc.username == "p_user"
    assert recovered_person.display_name == "P User"

def test_duplicate_username_constraint(temp_db_path):
    store = SQLiteStore(temp_db_path)
    acc_reg = AccountRegistry(store)
    
    acc_reg.create_account("dup_user", "hash", "salt", "USER")
    
    with pytest.raises(ValueError, match="already exists"):
        acc_reg.create_account("DUP_USER", "hash", "salt", "USER")

def test_delete_cascade_persistence(temp_db_path):
    store = SQLiteStore(temp_db_path)
    acc_reg = AccountRegistry(store)
    person_reg = PersonRegistry(store)
    
    acc = acc_reg.create_account("del_user", "hash", "salt", "USER")
    person = person_reg.create_person("Del User", account_id=acc.account_id, role="USER")
    
    # Delete person directly
    person_reg.remove_person(person.atlas_person_id)
    
    assert len(store.get_all_persons()) == 0
    assert len(store.get_all_accounts()) == 1
    
    # Delete account directly
    acc_reg.remove_account(acc.account_id)
    
    assert len(store.get_all_accounts()) == 0
