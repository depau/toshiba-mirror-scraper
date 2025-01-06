import Fuse from 'npm:fuse.js@7.0.0';
import {tqdm} from "npm:@thesephist/tsqdm";

const dataDir = Deno.env.get('DATA_DIR') || './data';
const productsDataset = [];
const contentDataset = [];

async function unwrapIterator(iterator) {
    const result = [];
    for await (const item of iterator) {
        result.push(item);
    }
    return result;
}

console.log("Loading products...");
for await (const entry of tqdm(await unwrapIterator(await Deno.readDir(dataDir + '/products'), {label: 'Products'}))) {
    if (!entry.isFile || !entry.name.endsWith('.json'))
        continue;
    const filePath = `${dataDir}/products/${entry.name}`;
    const fileContent = await Deno.readTextFile(filePath);
    const product = JSON.parse(fileContent);

    productsDataset.push({
        id: product.mid,
        ty: 'p',
        na: `${product.family} ${product.name}`,
        pl: product.type,
    });
}

// Write the raw search dataset to a file
const productsDatasetFile = `${dataDir}/products_dataset.json`;
await Deno.writeTextFile(productsDatasetFile, JSON.stringify(productsDataset));
console.log(`Raw search dataset written to ${productsDatasetFile}`);

const productsIndex = Fuse.createIndex(['na'], productsDataset);

const productsIndexFile = `${dataDir}/products_index.json`;
await Deno.writeTextFile(productsIndexFile, JSON.stringify(productsIndex.toJSON()));
console.log(`Search index written to ${productsIndexFile}`);

console.log("Loading content...");
for await (const entry of tqdm(await unwrapIterator(Deno.readDir(dataDir + '/content'), {label: 'Content'}))) {
    if (!entry.isFile || !entry.name.endsWith('.json') || entry.name.endsWith('_crawl_result.json'))
        continue;
    const filePath = `${dataDir}/content/${entry.name}`;
    const fileContent = await Deno.readTextFile(filePath);
    const content = JSON.parse(fileContent);

    if (content.contentID == null || content.contentType == null)
        continue;

    contentDataset.push({
        id: content.contentID,
        ty: 'c',
        na: content.heading ?? content.title ?? content.contentFile.split('/').pop() ?? contentID,
        ct: content.contentType,
    });
}

const contentDatasetFile = `${dataDir}/content_dataset.json`;
await Deno.writeTextFile(contentDatasetFile, JSON.stringify(contentDataset));
console.log(`Raw search dataset written to ${contentDatasetFile}`);

const contentIndex = Fuse.createIndex(['na'], contentDataset);

const contentIndexFile = `${dataDir}/content_index.json`;
await Deno.writeTextFile(contentIndexFile, JSON.stringify(contentIndex.toJSON()));
console.log(`Search index written to ${contentIndexFile}`);