import asyncpg


async def test_cluster_explicitly_disables_unix_sockets(postgres_url):
    connection = await asyncpg.connect(postgres_url)
    try:
        sockets = await connection.fetchrow(
            "SELECT setting, source FROM pg_settings WHERE name = 'unix_socket_directories'"
        )
        assert sockets["setting"] == ""
        # Windows already defaults to no Unix sockets. Require an explicit
        # setting so that a Windows pass also guards Linux package defaults.
        assert sockets["source"] == "configuration file"
        assert str(await connection.fetchval("SELECT inet_server_addr()")) == "127.0.0.1"
    finally:
        await connection.close()
