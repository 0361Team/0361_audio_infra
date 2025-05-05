from pinecone import Pinecone



if __name__ == '__main__':

    pc = Pinecone(api_key="")
    index_name = "multilingual-e5-large"
    # pc.create_index_for_model(
    #     name=index_name,
    #     cloud="aws",
    #     region="us-east-1",
    #     embed={
    #         "model": "multilingual-e5-large",
    #         "field_map": {
    #             "text": "text"  # Map the record field to be embedded
    #         }
    #     }
    # )
    index = pc.Index(index_name)

    from  src.parse_data import txt_to_records,batch_with_itertools
    records = txt_to_records('../data/인공지능 0414.txt', 'ai')

    records = batch_with_itertools(records, batch_size=96)
    for record in records:
        index.upsert_records(
            namespace="example-namespace",
            records=record
        )

    query_payload = {
        "inputs": {
            "text": "Tell me about '배치노멀라이제이션'."
        },
        "top_k": 3
    }

    results = index.search(
        namespace="example-namespace",
        query=query_payload
    )

    print(results)






