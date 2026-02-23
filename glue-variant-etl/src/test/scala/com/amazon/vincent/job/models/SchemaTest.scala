// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.models

import com.amazon.vincent.job.models.Schema.{
  MutationStruct,
  VariantSchemaWithAnno,
  VariantSchemaWithInfoAndAnno,
  VepStruct
}
import org.apache.spark.sql.test.SharedSparkSession
import org.apache.spark.sql.{QueryTest, Row}
import org.junit.runner.RunWith
import org.scalatestplus.junit.JUnitRunner

@RunWith(classOf[JUnitRunner])
class SchemaTest extends QueryTest with SharedSparkSession {

  def createVariantSchemaData(annotationsField: Row): Row = {
    Row(
      "importjobid",
      "contigname",
      100,
      1000,
      List("names"),
      "referenceallele",
      List("A", "T"),
      1.0,
      List("filterA", "filterB"),
      false,
      Map("attributeA" -> "valueA"),
      true,
      List(1, 1),
      List(1.0, 1.0),
      List(1, 1),
      List(1, 1),
      1,
      List(1, 1),
      1,
      1,
      "sampleA",
      Map("informationA" -> "InfomationB"),
      annotationsField)
  }

  def createVepEntry(extras: Map[String, String]): Row = {
    Row(
      "allele",
      List("consequenceA", "consequenceB"),
      "impact",
      "symbol",
      "gene",
      "feature_type",
      "feature",
      "biotype",
      Row("1", "10"),
      Row("1", "10"),
      "hgvsc",
      "hgvsp",
      "cdna_position",
      "cds_position",
      "protein_position",
      Row("A", "T"),
      Row("A", "T"),
      List("existing_variation_a", "existing_variation_b"),
      "distance",
      "strand",
      List("flagA", "flagB"),
      "symbol_source",
      "hgnc_id",
      extras)
  }

  test("Ensure schema VariantSchemaWithAnno names are correct") {
    val expected = Set(
      "importjobid",
      "contigname",
      "start",
      "end",
      "names",
      "referenceallele",
      "alternatealleles",
      "qual",
      "filters",
      "splitfrommultiallelic",
      "attributes",
      "phased",
      "calls",
      "genotypelikelihoods",
      "phredlikelihoods",
      "alleledepths",
      "conditionalquality",
      "spl",
      "depth",
      "ps",
      "sampleid",
      "annotations")
    assertResult(expected)(VariantSchemaWithAnno.fieldNames.toSet)
  }

  test("Ensure schema VariantSchemaWithInfoAndAnno names are correct") {
    val expected = Set(
      "importjobid",
      "contigname",
      "start",
      "end",
      "names",
      "referenceallele",
      "alternatealleles",
      "qual",
      "filters",
      "splitfrommultiallelic",
      "attributes",
      "phased",
      "calls",
      "genotypelikelihoods",
      "phredlikelihoods",
      "alleledepths",
      "conditionalquality",
      "spl",
      "depth",
      "ps",
      "sampleid",
      "information",
      "annotations")

    assertResult(expected)(VariantSchemaWithInfoAndAnno.fieldNames.toSet)
  }

  test("Ensure VepEntries names are correct") {
    val expected = Set(
      "allele",
      "consequence",
      "impact",
      "symbol",
      "gene",
      "feature_type",
      "feature",
      "biotype",
      "exon",
      "intron",
      "hgvsc",
      "hgvsp",
      "cdna_position",
      "cds_position",
      "protein_position",
      "amino_acids",
      "codons",
      "existing_variation",
      "distance",
      "strand",
      "flags",
      "symbol_source",
      "hgnc_id",
      "extras")

    assertResult(expected)(VepStruct.fieldNames.toSet)
  }

  test("test mutationStruct Struct") {
    val data = Row("A", "T") :: Row("G", "C") :: Row(null, null) :: Nil
    val df = spark.createDataFrame(spark.sparkContext.parallelize(data), MutationStruct)
    checkAnswer(df, data)
  }

  test("test rankValueStruct Struct") {
    val data = Row("1", "10") :: Row("2", "10") :: Row(null, null) :: Nil
    val df = spark.createDataFrame(spark.sparkContext.parallelize(data), MutationStruct)
    checkAnswer(df, data)
  }

  test("test vepStruct") {
    val rowA = createVepEntry(Map("keyA" -> "valueA"))
    val rowB = createVepEntry(Map("keyB" -> "valueB"))
    val rowC = Row(Seq.fill(rowB.length)(null): _*)
    // Try with different keys
    val data = rowA :: rowB :: rowC :: Nil
    val df = spark.createDataFrame(spark.sparkContext.parallelize(data), VepStruct)
    checkAnswer(df, data)
  }

  test("VCF with annotation") {
    val entryA = createVepEntry(Map("keyA" -> "valueA"))
    val entryB = createVepEntry(Map("keyB" -> "valueB"))
    val data = createVariantSchemaData(Row(List(entryA, entryB)))
    val df = spark.createDataFrame(
      spark.sparkContext.parallelize(data :: Nil),
      VariantSchemaWithInfoAndAnno)
    checkAnswer(df, data)
  }
}
