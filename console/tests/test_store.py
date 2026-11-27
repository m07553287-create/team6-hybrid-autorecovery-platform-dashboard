import fakeredis

from console.store import Store


def test_touch_list_drop_roundtrip():
    st = Store(fakeredis.FakeRedis(decode_responses=True), host="s1")
    st.touch("정다운", "db-01", "free -h", 1000, 1001)
    st.touch("정다운", "k8s-cp1", "", 1000, 1002)
    rows = {r["target"]: r for r in st.list("정다운")}
    assert set(rows) == {"db-01", "k8s-cp1"}
    assert rows["db-01"]["last_cmd"] == "free -h" and rows["db-01"]["host"] == "s1"
    st.drop("정다운", "db-01")
    assert {r["target"] for r in st.list("정다운")} == {"k8s-cp1"}


def test_list_empty():
    st = Store(fakeredis.FakeRedis(decode_responses=True))
    assert st.list("nobody") == []
