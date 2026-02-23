// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.models

import org.apache.spark.sql.types.{
  ArrayType,
  BooleanType,
  DoubleType,
  IntegerType,
  MapType,
  StringType,
  StructField,
  StructType
}

object Schema {

  private val VariantSchemaFields = Array(
    StructField("importjobid", StringType, nullable = true),
    StructField("contigname", StringType, nullable = true),
    StructField("start", IntegerType, nullable = true),
    StructField("end", IntegerType, nullable = true),
    StructField("names", ArrayType(StringType, containsNull = true), nullable = true),
    StructField("referenceallele", StringType, nullable = true),
    StructField("alternatealleles", ArrayType(StringType, containsNull = true), nullable = true),
    StructField("qual", DoubleType, nullable = true),
    StructField("filters", ArrayType(StringType, containsNull = true), nullable = true),
    StructField("splitfrommultiallelic", BooleanType, nullable = true),
    StructField(
      "attributes",
      MapType(StringType, StringType, valueContainsNull = true),
      nullable = true),
    StructField("phased", BooleanType, nullable = true),
    StructField("calls", ArrayType(IntegerType, containsNull = true), nullable = true),
    StructField(
      "genotypelikelihoods",
      ArrayType(DoubleType, containsNull = true),
      nullable = true),
    StructField("phredlikelihoods", ArrayType(IntegerType, containsNull = true), nullable = true),
    StructField("alleledepths", ArrayType(IntegerType, containsNull = true), nullable = true),
    StructField("conditionalquality", IntegerType, nullable = true),
    StructField("spl", ArrayType(IntegerType, containsNull = true), nullable = true),
    StructField("depth", IntegerType, nullable = true),
    StructField("ps", IntegerType, nullable = true),
    StructField("sampleid", StringType, nullable = true))

  val MutationStruct: StructType = StructType(
    Seq(
      StructField("reference", StringType, nullable = true),
      StructField("variant", StringType, nullable = true)))

  val RankValueStruct: StructType = StructType(
    Seq(
      StructField("rank", StringType, nullable = true),
      StructField("total", StringType, nullable = true)))

  // the fields for vep struct should match schema defined in
  // src/main/kotlin/com/amazon/aws/vincent/data/schema/VariantStoreSchema.kt
  val VepStruct: StructType = StructType(
    Seq(
      StructField("allele", StringType, nullable = true),
      StructField("consequence", ArrayType(StringType, containsNull = true), nullable = true),
      StructField("impact", StringType, nullable = true),
      StructField("symbol", StringType, nullable = true),
      StructField("gene", StringType, nullable = true),
      StructField("feature_type", StringType, nullable = true),
      StructField("feature", StringType, nullable = true),
      StructField("biotype", StringType, nullable = true),
      StructField("exon", RankValueStruct, nullable = true),
      StructField("intron", RankValueStruct, nullable = true),
      StructField("hgvsc", StringType, nullable = true),
      StructField("hgvsp", StringType, nullable = true),
      StructField("cdna_position", StringType, nullable = true),
      StructField("cds_position", StringType, nullable = true),
      StructField("protein_position", StringType, nullable = true),
      StructField("amino_acids", MutationStruct, nullable = true),
      StructField("codons", MutationStruct, nullable = true),
      StructField(
        "existing_variation",
        ArrayType(StringType, containsNull = true),
        nullable = true),
      StructField("distance", StringType, nullable = true),
      StructField("strand", StringType, nullable = true),
      StructField("flags", ArrayType(StringType, containsNull = true), nullable = true),
      StructField("symbol_source", StringType, nullable = true),
      StructField("hgnc_id", StringType, nullable = true),
      StructField(
        "extras",
        MapType(StringType, StringType, valueContainsNull = true),
        nullable = true)))

  val AnnotationsStructType: StructType = StructType(
    Seq(StructField("vep", ArrayType(VepStruct, containsNull = true), nullable = true)))

  val AnnotationsFieldStruct: StructField =
    StructField("annotations", AnnotationsStructType, nullable = true)

  private val InformationField =
    StructField(
      "information",
      MapType(StringType, StringType, valueContainsNull = true),
      nullable = true)

  val VariantSchema: StructType = StructType(VariantSchemaFields)

  val VariantSchemaWithInfo: StructType = StructType(VariantSchemaFields :+ InformationField)

  val VariantSchemaWithAnno = StructType(VariantSchemaFields :+ AnnotationsFieldStruct)

  val VariantSchemaWithInfoAndAnno: StructType = StructType(
    VariantSchemaWithInfo :+ AnnotationsFieldStruct)

}
